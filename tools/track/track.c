// Dark-object tracker for the OV9281 at 640x400 Y8 (raw V4L2 capture via unicam).
// A pixel is dark if it is below its threshold: -r percent (default 50) of its mean over CALIB
// frames sampled during the first second, so static dark things (cables, corners) never count.
// Start with the object out of view or moving (an object that stays still for that second
// becomes background). -t sets one absolute threshold instead.
// Every frame: copy it out of the uncached DMA buffer, then find the object as a 4-connected
// blob of dark pixels with >= min_pixels whose pixels average below DARK_MAX of their
// threshold (black, not a shadow or a hand). If several qualify, take the one with the most
// darkness, sum(threshold - pixel). The centroid is the blob's mass average.
// Tracking: blobs are seeded only within +-SEARCH_R px of the last centroid plus the last
// velocity; if none qualifies there, the whole frame is searched.
// From the first detection on, record every frame and its centroid into RAM; on stop (buffer
// full or Ctrl-C) write <dir>/frames.raw (640x400 8-bit, concatenated), <dir>/track.csv and
// the threshold map <dir>/threshold.pgm (black = ignored).
//
// usage: track [-f fps] [-r percent | -t thresh] [-m min_pixels] [-n frames]
//              [-e exposure_lines] [-g gain] [-o dir]
//        track -p dir   replay a recording through the detector, writes <dir>/replay.csv
// build: gcc -O3 -Wall -o track track.c -lm
#include <errno.h>
#include <fcntl.h>
#include <getopt.h>
#include <linux/media-bus-format.h>
#include <linux/v4l2-subdev.h>
#include <linux/videodev2.h>
#include <math.h>
#include <poll.h>
#include <sched.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define W 640
#define H 400
#define FS (W * H)
#define NBUF 4
#define HBLANK 890            // driver minimum for this mode; line = (640 + 890) px
#define LINE_US (1530 / 192.0) // real R8 pixel clock is 192 MHz, not the 200 the driver reports
#define VBLANK_MIN 56         // below ~56 lines the sensor returns wrong pixel values
#define CALIB 25              // empty-scene samples, one every CALIB_STEP frames
#define CALIB_STEP 10
#define THR_MIN 15            // below this the pixel is too dark to see a darker object: ignore it
#define DARK_MAX 7 / 10       // blob pixels must average below this fraction of their threshold
#define SEARCH_R 40           // tracking window half-size, px; the throw test moved ~15 px/frame

typedef struct { uint32_t seq; uint64_t ts_us; uint32_t n; float cx, cy; uint8_t mode; uint16_t proc_us, lat_us; } rec_t;
typedef struct { uint32_t n; uint64_t sx, sy, sp, st; } blob_t;  // px, sum x, sum y, sum pixel, sum threshold

static volatile sig_atomic_t stop;
static void on_sigint(int s) { (void)s; stop = 1; }

static uint64_t now_us(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1000000ull + t.tv_nsec / 1000;
}

static void die(const char *what) { perror(what); exit(1); }

// Under sudo, hand written files back to the calling user.
static void chown_to_caller(const char *path) {
    const char *u = getenv("SUDO_UID"), *g = getenv("SUDO_GID");
    if (u && g && chown(path, atoi(u), atoi(g)) < 0) perror(path);
}

static void set_ctrl(int fd, uint32_t id, int32_t val, const char *name) {
    struct v4l2_control c = {.id = id, .value = val};
    if (ioctl(fd, VIDIOC_S_CTRL, &c) < 0) die(name);
}

static uint8_t thr_map[FS];
static uint16_t bg_sum[FS];
static uint16_t stamp[FS], cur;  // stamp[i] == cur: pixel already belongs to a blob this frame
static int32_t stack[FS];
static int nmin = 100;

// Flood-fill the 4-connected dark blob containing pixel i.
static blob_t fill(const uint8_t *p, int i) {
    blob_t b = {0};
    int sp = 0;
    stack[sp++] = i; stamp[i] = cur;
    while (sp) {
        int j = stack[--sp], x = j % W, y = j / W;
        b.n++; b.sx += x; b.sy += y; b.sp += p[j]; b.st += thr_map[j];
#define PUSH(k) if (stamp[k] != cur && p[k] < thr_map[k]) { stamp[k] = cur; stack[sp++] = k; }
        if (x > 0) PUSH(j - 1)
        if (x < W - 1) PUSH(j + 1)
        if (y > 0) PUSH(j - W)
        if (y < H - 1) PUSH(j + W)
    }
    return b;
}

// Best qualifying blob with a pixel inside [x0,x1) x [y0,y1); blobs are filled in full.
static int find(const uint8_t *p, int x0, int y0, int x1, int y1, blob_t *best) {
    int found = 0;
    x0 = x0 < 0 ? 0 : x0; y0 = y0 < 0 ? 0 : y0;
    x1 = x1 > W ? W : x1; y1 = y1 > H ? H : y1;
    for (int y = y0; y < y1; y++)
        for (int xs = x0; xs < x1; xs += 32) {
            int xe = xs + 32 < x1 ? xs + 32 : x1;
            const uint8_t *pr = p + y * W, *tr = thr_map + y * W;
            uint8_t any = 0;  // vectorised pre-check, almost every chunk has no dark pixel
            for (int x = xs; x < xe; x++) any |= pr[x] < tr[x];
            if (!any) continue;
            for (int i = y * W + xs; i < y * W + xe; i++) {
                if (p[i] >= thr_map[i] || stamp[i] == cur) continue;
                blob_t b = fill(p, i);
                if (b.n >= (uint32_t)nmin && b.sp < b.st * DARK_MAX &&
                    (!found || b.st - b.sp > best->st - best->sp)) { *best = b; found = 1; }
            }
        }
    return found;
}

// Returns 0 = not found, 1 = found in the tracking window, 2 = found by full-frame search.
static int track(const uint8_t *p, float *cx, float *cy, uint32_t *n) {
    static int have;
    static float lx, ly, vx, vy;
    blob_t b = {0};
    int mode = 0;
    if (++cur == 0) { memset(stamp, 0, sizeof stamp); cur = 1; }
    if (have) {
        int px = lroundf(lx + vx), py = lroundf(ly + vy);
        if (find(p, px - SEARCH_R, py - SEARCH_R, px + SEARCH_R + 1, py + SEARCH_R + 1, &b)) mode = 1;
    }
    if (!mode && find(p, 0, 0, W, H, &b)) mode = 2;
    if (!mode) { have = 0; *cx = *cy = NAN; *n = 0; return 0; }
    *cx = (float)b.sx / b.n; *cy = (float)b.sy / b.n; *n = b.n;
    vx = have ? *cx - lx : 0; vy = have ? *cy - ly : 0;
    lx = *cx; ly = *cy; have = 1;
    return mode;
}

static void replay(const char *dir) {
    char path[96];
    snprintf(path, sizeof path, "%s/threshold.pgm", dir);
    FILE *t = fopen(path, "rb");
    if (!t || fscanf(t, "P5 %*d %*d %*d") < 0 || fgetc(t) < 0 || fread(thr_map, FS, 1, t) != 1) die(path);
    fclose(t);
    snprintf(path, sizeof path, "%s/frames.raw", dir);
    FILE *f = fopen(path, "rb");
    if (!f) die(path);
    snprintf(path, sizeof path, "%s/replay.csv", dir);
    FILE *c = fopen(path, "w");
    if (!c) die(path);
    fprintf(c, "frame,blob_px,cx,cy,mode,proc_us\n");
    static uint8_t p[FS];
    int i = 0, modes[3] = {0}, proc_max = 0;
    uint64_t proc_sum = 0;
    for (; fread(p, FS, 1, f) == 1; i++) {
        float cx, cy;
        uint32_t n;
        uint64_t t0 = now_us();
        int mode = track(p, &cx, &cy, &n), proc = now_us() - t0;
        modes[mode]++; proc_sum += proc; proc_max = proc > proc_max ? proc : proc_max;
        fprintf(c, "%d,%u,%.2f,%.2f,%d,%d\n", i, n, cx, cy, mode, proc);
    }
    fclose(c);
    if (i) printf("%d frames: %d tracked in window, %d full search, %d not found; detect mean %.0f us, max %d us -> %s\n",
                  i, modes[1], modes[2], modes[0], (double)proc_sum / i, proc_max, path);
}

int main(int argc, char **argv) {
    double fps = 250;
    int thr = -1, ratio = 50, nmax = 1000, expo = -1, gain = -1, o;
    char dir[64], *replay_dir = NULL;
    time_t now = time(NULL);
    strftime(dir, sizeof dir, "rec_%Y%m%d_%H%M%S", localtime(&now));
    while ((o = getopt(argc, argv, "f:r:t:m:n:e:g:o:p:")) != -1) switch (o) {
        case 'f': fps = atof(optarg); break;
        case 'r': ratio = atoi(optarg); break;
        case 't': thr = atoi(optarg); break;
        case 'm': nmin = atoi(optarg); break;
        case 'n': nmax = atoi(optarg); break;
        case 'e': expo = atoi(optarg); break;
        case 'g': gain = atoi(optarg); break;
        case 'o': snprintf(dir, sizeof dir, "%s", optarg); break;
        case 'p': replay_dir = optarg; break;
        default: fprintf(stderr, "usage: %s [-f fps] [-r percent | -t thresh] [-m min_pixels] "
                                 "[-n frames] [-e exposure_lines] [-g gain] [-o dir] | -p dir\n", argv[0]); return 1;
    }
    if (replay_dir) { replay(replay_dir); return 0; }
    // frame = (VTS + 0.95) lines, VTS = 400 + vblank
    int vblank = (int)lround(1e6 / fps / LINE_US - 0.95) - H;
    if (vblank < VBLANK_MIN) { fprintf(stderr, "fps too high: max %.1f\n", 1e6 / ((H + VBLANK_MIN + 0.95) * LINE_US)); return 1; }
    int vts = H + vblank;
    if (expo < 0) expo = vts - 30;
    if (expo > vts - 30) { fprintf(stderr, "exposure max is %d lines at this fps\n", vts - 30); return 1; }

    // Record buffer, touched up front so recording causes no page faults.
    uint8_t *frames = malloc((size_t)nmax * FS);
    rec_t *log = calloc(nmax, sizeof *log);
    if (!frames || !log) die("malloc");
    memset(frames, 0, (size_t)nmax * FS);
    if (mlockall(MCL_CURRENT | MCL_FUTURE) < 0) perror("mlockall (run with sudo for real-time)");
    struct sched_param sp = {.sched_priority = 50};
    if (sched_setscheduler(0, SCHED_FIFO, &sp) < 0) perror("SCHED_FIFO (run with sudo for real-time)");

    int sd = open("/dev/v4l-subdev0", O_RDWR), fd = open("/dev/video0", O_RDWR);
    if (sd < 0 || fd < 0) die("open camera");
    struct v4l2_subdev_format sf = {.which = V4L2_SUBDEV_FORMAT_ACTIVE, .pad = 0};
    sf.format = (struct v4l2_mbus_framefmt){.width = W, .height = H, .code = MEDIA_BUS_FMT_Y8_1X8, .field = V4L2_FIELD_NONE};
    if (ioctl(sd, VIDIOC_SUBDEV_S_FMT, &sf) < 0) die("subdev format");
    struct v4l2_format f = {.type = V4L2_BUF_TYPE_VIDEO_CAPTURE};
    f.fmt.pix = (struct v4l2_pix_format){.width = W, .height = H, .pixelformat = V4L2_PIX_FMT_GREY, .field = V4L2_FIELD_NONE};
    if (ioctl(fd, VIDIOC_S_FMT, &f) < 0) die("video format");
    int bpl = f.fmt.pix.bytesperline;
    set_ctrl(sd, V4L2_CID_HBLANK, HBLANK, "hblank");
    set_ctrl(sd, V4L2_CID_VBLANK, vblank, "vblank");
    set_ctrl(sd, V4L2_CID_EXPOSURE, expo, "exposure");
    if (gain >= 0) set_ctrl(sd, V4L2_CID_ANALOGUE_GAIN, gain, "gain");
    struct v4l2_control gc = {.id = V4L2_CID_ANALOGUE_GAIN};
    ioctl(sd, VIDIOC_G_CTRL, &gc);
    char thr_s[24];
    if (thr >= 0) snprintf(thr_s, sizeof thr_s, "%d", thr);
    else snprintf(thr_s, sizeof thr_s, "%d%% of empty scene", ratio);

    struct v4l2_requestbuffers rb = {.count = NBUF, .type = V4L2_BUF_TYPE_VIDEO_CAPTURE, .memory = V4L2_MEMORY_MMAP};
    if (ioctl(fd, VIDIOC_REQBUFS, &rb) < 0) die("reqbufs");
    uint8_t *map[NBUF];
    for (int i = 0; i < NBUF; i++) {
        struct v4l2_buffer b = {.index = i, .type = rb.type, .memory = rb.memory};
        if (ioctl(fd, VIDIOC_QUERYBUF, &b) < 0) die("querybuf");
        map[i] = mmap(NULL, b.length, PROT_READ, MAP_SHARED, fd, b.m.offset);
        if (map[i] == MAP_FAILED) die("mmap");
        if (ioctl(fd, VIDIOC_QBUF, &b) < 0) die("qbuf");
    }
    signal(SIGINT, on_sigint);
    int type = rb.type;
    if (ioctl(fd, VIDIOC_STREAMON, &type) < 0) die("streamon");
    printf("640x400 @ %.2f fps (vblank %d), exposure %d lines (%.2f ms), gain %d, thresh %s, min %d px, "
           "recording up to %d frames (%.1f s) to %s/ once detected. Ctrl-C to stop.\n",
           1e6 / ((vts + 0.95) * LINE_US), vblank, expo, expo * LINE_US / 1000, gc.value, thr_s, nmin, nmax,
           nmax / fps, dir);
    int calib = thr < 0 ? CALIB * CALIB_STEP : 0;
    memset(thr_map, thr < 0 ? 0 : thr > 255 ? 255 : thr, FS);

    // Until the first detection, every frame is copied into slot 0 and overwritten.
    int nrec = 0, recording = 0, total = 0, gaps = 0, proc_max = 0;
    uint32_t last_seq = 0;
    uint64_t proc_sum = 0, copy_sum = 0, t_print = now_us();
    while (!stop && nrec < nmax) {
        struct pollfd pf = {.fd = fd, .events = POLLIN};
        int pr = poll(&pf, 1, 1000);
        if (pr < 0 && errno == EINTR) continue;
        if (pr <= 0) { fprintf(stderr, "no frame for 1 s, stream hung\n"); break; }
        struct v4l2_buffer b = {.type = rb.type, .memory = rb.memory};
        if (ioctl(fd, VIDIOC_DQBUF, &b) < 0) { if (errno == EINTR) continue; die("dqbuf"); }
        uint64_t t0 = now_us(), ts = b.timestamp.tv_sec * 1000000ull + b.timestamp.tv_usec;
        uint32_t seq = b.sequence;  // QBUF below overwrites b
        uint8_t *dst = frames + (size_t)nrec * FS;
        if (bpl == W) memcpy(dst, map[b.index], FS);
        else for (int y = 0; y < H; y++) memcpy(dst + y * W, map[b.index] + y * bpl, W);
        if (ioctl(fd, VIDIOC_QBUF, &b) < 0) die("qbuf");
        if (calib) {
            if (calib % CALIB_STEP == 0) for (int i = 0; i < FS; i++) bg_sum[i] += dst[i];
            if (--calib == 0) {
                int blind = 0;
                for (int i = 0; i < FS; i++) {
                    int t = bg_sum[i] * ratio / (100 * CALIB);
                    thr_map[i] = t < THR_MIN ? 0 : t;
                    blind += t < THR_MIN;
                }
                printf("empty scene calibrated; %d px (%.1f%%) are too dark to detect anything\n",
                       blind, 100.0 * blind / FS);
            }
            continue;
        }
        uint64_t t1 = now_us();
        float cx, cy;
        uint32_t n;
        int mode = track(dst, &cx, &cy, &n), proc = now_us() - t0;

        if (total && seq != last_seq + 1) gaps += seq - last_seq - 1;
        last_seq = seq; total++;
        proc_sum += proc; copy_sum += t1 - t0; if (proc > proc_max) proc_max = proc;
        if (!recording && mode) { recording = 1; printf("detected at seq %u, recording\n", seq); }
        if (recording) log[nrec++] = (rec_t){seq, ts, n, cx, cy, mode, proc, t0 - ts};
        if (t0 - t_print > 500000) {
            t_print = t0;
            printf("seq %6u  blob px %6u  centroid %6.1f %6.1f  %s  proc %4d us (max %d)  drops %d  rec %d\n",
                   seq, n, cx, cy, mode == 1 ? "tracked" : mode == 2 ? "search " : "lost   ", proc, proc_max, gaps, nrec);
            fflush(stdout);
        }
    }
    ioctl(fd, VIDIOC_STREAMOFF, &type);
    if (total) printf("%d frames, %d dropped, processing mean %.0f us (copy %.0f, detect %.0f) max %d us\n",
                      total, gaps, (double)proc_sum / total, (double)copy_sum / total,
                      (double)(proc_sum - copy_sum) / total, proc_max);
    if (!nrec) { printf("nothing detected, nothing written\n"); return 0; }

    mkdir(dir, 0755);
    chown_to_caller(dir);
    char path[96];
    snprintf(path, sizeof path, "%s/track.csv", dir);
    FILE *c = fopen(path, "w");
    if (!c) die(path);
    fprintf(c, "frame,seq,ts_us,blob_px,cx,cy,mode,proc_us,dq_minus_ts_us\n");
    for (int i = 0; i < nrec; i++)
        fprintf(c, "%d,%u,%llu,%u,%.2f,%.2f,%u,%u,%u\n", i, log[i].seq, (unsigned long long)log[i].ts_us,
                log[i].n, log[i].cx, log[i].cy, log[i].mode, log[i].proc_us, log[i].lat_us);
    fclose(c);
    chown_to_caller(path);
    snprintf(path, sizeof path, "%s/frames.raw", dir);
    FILE *r = fopen(path, "wb");
    if (!r || fwrite(frames, FS, nrec, r) != (size_t)nrec) die(path);
    fclose(r);
    chown_to_caller(path);
    snprintf(path, sizeof path, "%s/threshold.pgm", dir);
    r = fopen(path, "wb");
    if (!r) die(path);
    fprintf(r, "P5 %d %d 255\n", W, H);
    fwrite(thr_map, FS, 1, r);
    fclose(r);
    chown_to_caller(path);
    printf("wrote %d frames to %s/\n", nrec, dir);
    return 0;
}
