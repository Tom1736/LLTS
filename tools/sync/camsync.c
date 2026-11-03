// camsync: lock the OV9281's frame timing to a shared reference pulse (vblank phase lock).
//
// The Pi 3 makes the reference with its hardware PWM (pulse.sh, GPIO18). The same wire goes to
// GPIO17 on both Pis, and both run this program. Each Pi timestamps the rising edges in its own
// CLOCK_MONOTONIC (kernel IRQ timestamps from the GPIO chardev) and steers its own sensor so a
// frame starts a fixed offset after every edge and N - 1 more frames are evenly spaced between edges.
// The default offset is 0.35 frame, so the edge lands at 65 % of a frame: on the single-core Pi Zero
// a frame-start interrupt that coincides with the edge interrupt delays one of the two timestamps
// by ~20 us. Both Pis use the same offset, so the cameras stay aligned.
// The two sensors never talk to each other: they only share the edges, so the result does not
// depend on NTP, network latency or the Pis' crystals.
//
// Steering: the frame period is (VTS + 0.95) lines, VTS = 400 + vblank. A vblank written after
// dequeuing frame n sets the interval frame n+1 -> n+2 (see test-results-2026-10-29.md, test 5).
// Each frame we predict the phase error of frame n+1 (its interval is already fixed) and pick the
// integer vblank for n+1 -> n+2 that removes a fraction G of it. The line time is learnt from the
// measured intervals, which absorbs the sensor crystal's ppm error. Phase is quantised to one
// line (8 us), so the error dithers within about +-4 us.
//
// Exposure defaults to the longest the lock allows (VTS - 30 - SLACK lines). SLACK lines are
// what the loop may shorten a frame by; it may lengthen without limit.
//
// For the screen flash test every frame is reduced to a 32x20 grid of 20x20 px cell sums
// (every 2nd row), so a minute of recording is ~8 MB even on the Pi Zero.
//
// Output in <dir>/: frames.csv, edges.csv, cells.u16 (GX*GY uint16 per frame), meta.txt, snap.pgm
//
// usage: sudo ./camsync [-f fps] [-p pulse_hz] [-e exposure_lines] [-g gain] [-o offset_us]
//                       [-t seconds] [-l gpio_line] [-c gpiochip] [-u] [-s] [-d dir]
//   -u   free-run: measure the phase against the pulse but never steer (baseline)
//   -s   synthetic reference: exact edges every 1/pulse_hz in this Pi's clock, no GPIO (loop test)
// build: gcc -O2 -Wall -o camsync camsync.c -lm
#include <errno.h>
#include <fcntl.h>
#include <getopt.h>
#include <linux/gpio.h>
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
#define NBUF 4
#define HBLANK 890                  // line = (640 + 890) px
#define LINE_NS (1530 / 0.192)      // real R8 pixel clock is 192 MHz: 7968.75 ns
#define VBLANK_MIN 56               // below ~56 lines the sensor returns wrong pixel values
#define SLACK 20                    // lines the loop may shorten a frame by
#define G 0.5                       // fraction of the predicted phase error removed per frame
#define GX 32
#define GY 20
#define CELL (W / GX)               // 20 px, square cells
#define ROWSTEP 2
#define EDGE_A 0.3                  // edge grid filter: phase gain
#define EDGE_B 0.05                 //                   period gain
#define EDGE_OUTLIER 300e3          // ns; an edge this far off the grid is ignored
#define LOCK_US 50.0                // |e| below this for LOCK_FRAMES frames = locked
#define LOCK_FRAMES 10

typedef struct { uint32_t seq; int64_t ts; int64_t k; int32_t m; float e_us; int16_t vb; uint8_t locked; } frec_t;
typedef struct { int64_t ts; int64_t k; double est, r; uint8_t used; } erec_t;

static volatile sig_atomic_t stop;
static void on_sigint(int s) { (void)s; stop = 1; }
static void die(const char *what) { perror(what); exit(1); }

static int64_t now_ns(clockid_t c) {
    struct timespec t;
    clock_gettime(c, &t);
    return t.tv_sec * 1000000000ll + t.tv_nsec;
}

static void chown_to_caller(const char *path) {
    const char *u = getenv("SUDO_UID"), *g = getenv("SUDO_GID");
    if (u && g && chown(path, atoi(u), atoi(g)) < 0) perror(path);
}

static void set_ctrl(int fd, uint32_t id, int32_t val, const char *name) {
    struct v4l2_control c = {.id = id, .value = val};
    if (ioctl(fd, VIDIOC_S_CTRL, &c) < 0) die(name);
}

// Reference edge grid, times in ns relative to t0 (doubles keep sub-ns precision for hours).
static int64_t t0;
static int nedge, outl;
static int64_t ek = -1;          // local index of the latest accepted edge
static double e_hat, tp_hat;     // filtered time of edge ek, filtered edge period
static int64_t last_edge_raw;

static erec_t *elog;
static int nelog, nelog_max;

static void on_edge(int64_t ts_abs, double tp_nom) {
    double ts = ts_abs - t0;
    erec_t rec = {.ts = ts_abs};
    last_edge_raw = ts_abs;
    if (nedge == 0) {
        e_hat = ts; tp_hat = tp_nom; ek++; nedge = 1; rec.used = 1;
    } else {
        int64_t n = llround((ts - e_hat) / tp_hat);
        if (n < 1) n = 1;
        double pred = e_hat + n * tp_hat, r = ts - pred;
        rec.r = r;
        if (nedge >= 4 && fabs(r) > EDGE_OUTLIER) {
            if (++outl >= 3) {  // the grid itself is wrong (pulse restarted?): start over
                fprintf(stderr, "edge grid lost (residual %.0f us), restarting\n", r / 1e3);
                e_hat = ts; tp_hat = tp_nom; ek += n; nedge = 1; outl = 0; rec.used = 1;
            }
        } else {
            outl = 0;
            if (nedge < 4) { tp_hat = (ts - e_hat) / n; e_hat = ts; }
            else { e_hat = pred + EDGE_A * r; tp_hat += EDGE_B * r / n; }
            ek += n; nedge++; rec.used = 1;
        }
    }
    rec.k = ek; rec.est = e_hat;
    if (nelog < nelog_max) elog[nelog++] = rec;
}

int main(int argc, char **argv) {
    double fps = 100, pulse_hz = 10, off_us = NAN, secs = 60;
    int expo = -1, gain = -1, line = 17, freerun = 0, synth = 0, o;
    const char *chip = "/dev/gpiochip0";
    char dir[96], host[32] = "pi";
    gethostname(host, sizeof host - 1);
    time_t now = time(NULL);
    char stamp[32];
    strftime(stamp, sizeof stamp, "%Y%m%d_%H%M%S", localtime(&now));
    snprintf(dir, sizeof dir, "sync_%s_%s", host, stamp);
    while ((o = getopt(argc, argv, "f:p:e:g:o:t:l:c:usd:")) != -1) switch (o) {
        case 'f': fps = atof(optarg); break;
        case 'p': pulse_hz = atof(optarg); break;
        case 'e': expo = atoi(optarg); break;
        case 'g': gain = atoi(optarg); break;
        case 'o': off_us = atof(optarg); break;
        case 't': secs = atof(optarg); break;
        case 'l': line = atoi(optarg); break;
        case 'c': chip = optarg; break;
        case 'u': freerun = 1; break;
        case 's': synth = 1; break;
        case 'd': snprintf(dir, sizeof dir, "%s", optarg); break;
        default:
            fprintf(stderr, "usage: %s [-f fps] [-p pulse_hz] [-e exposure_lines] [-g gain] [-o offset_us] "
                            "[-t seconds] [-l gpio_line] [-c gpiochip] [-u] [-s] [-d dir]\n", argv[0]);
            return 1;
    }
    int N = (int)lround(fps / pulse_hz);
    if (N < 1 || fabs(N * pulse_hz - fps) > 1e-6 * fps) {
        fprintf(stderr, "fps must be an integer multiple of the pulse rate\n"); return 1;
    }
    double tp_nom = 1e9 / pulse_hz, T_nom = tp_nom / N;
    if (isnan(off_us)) off_us = 0.35 * T_nom / 1e3;
    int v0 = (int)lround(T_nom / LINE_NS - 0.95) - H;
    if (v0 < VBLANK_MIN + SLACK) {
        fprintf(stderr, "fps too high: max %.1f\n", 1e9 / ((H + VBLANK_MIN + SLACK + 0.95) * LINE_NS)); return 1;
    }
    if (expo < 0) expo = H + v0 - 30 - SLACK;
    int vb_min = expo + 30 - H;
    if (vb_min < VBLANK_MIN) vb_min = VBLANK_MIN;
    if (vb_min > v0) { fprintf(stderr, "exposure max is %d lines at this fps\n", H + v0 - 30); return 1; }
    int vb_max = v0 + (int)lround(T_nom / LINE_NS);
    int nmax = (int)(secs * fps) + 16;

    frec_t *flog = calloc(nmax, sizeof *flog);
    uint16_t *cells = calloc((size_t)nmax * GX * GY, sizeof *cells);
    nelog_max = (int)(secs * pulse_hz) + 64;
    elog = calloc(nelog_max, sizeof *elog);
    static uint8_t row[W], snap[W * H];
    if (!flog || !cells || !elog) die("calloc");
    if (mlockall(MCL_CURRENT | MCL_FUTURE) < 0) perror("mlockall (run with sudo for real-time)");
    struct sched_param sp = {.sched_priority = 50};
    if (sched_setscheduler(0, SCHED_FIFO, &sp) < 0) perror("SCHED_FIFO (run with sudo for real-time)");

    // Reference input: rising edges, kernel timestamps in CLOCK_MONOTONIC, pulled down so an
    // unconnected wire reads as "no pulse" instead of noise.
    int cfd = synth ? -1 : open(chip, O_RDWR);
    if (!synth && cfd < 0) die(chip);
    struct gpio_v2_line_request req = {.num_lines = 1, .event_buffer_size = 64};
    req.offsets[0] = line;
    snprintf(req.consumer, sizeof req.consumer, "camsync");
    req.config.flags = GPIO_V2_LINE_FLAG_INPUT | GPIO_V2_LINE_FLAG_EDGE_RISING | GPIO_V2_LINE_FLAG_BIAS_PULL_DOWN;
    if (!synth && ioctl(cfd, GPIO_V2_GET_LINE_IOCTL, &req) < 0) {
        req.config.flags &= ~GPIO_V2_LINE_FLAG_BIAS_PULL_DOWN;
        if (ioctl(cfd, GPIO_V2_GET_LINE_IOCTL, &req) < 0) die("gpio line request");
    }
    int gfd = synth ? -1 : req.fd;  // poll ignores a negative fd

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
    set_ctrl(sd, V4L2_CID_VBLANK, v0, "vblank");
    set_ctrl(sd, V4L2_CID_EXPOSURE, expo, "exposure");
    if (gain >= 0) set_ctrl(sd, V4L2_CID_ANALOGUE_GAIN, gain, "gain");
    struct v4l2_control gc = {.id = V4L2_CID_ANALOGUE_GAIN};
    ioctl(sd, VIDIOC_G_CTRL, &gc);

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
    signal(SIGTERM, on_sigint);
    t0 = now_ns(CLOCK_MONOTONIC);
    int64_t real_minus_mono = now_ns(CLOCK_REALTIME) - t0;
    int type = rb.type;
    if (ioctl(fd, VIDIOC_STREAMON, &type) < 0) die("streamon");
    printf("%s: 640x400 @ %.3f fps, pulse %.3f Hz on %s line %d (N = %d), vblank %d [%d..%d], exposure %d lines "
           "(%.2f ms), gain %d, offset %.1f us, %s%s, %.0f s -> %s/\n",
           host, fps, pulse_hz, chip, line, N, v0, vb_min, vb_max, expo, expo * LINE_NS / 1e6, gc.value, off_us,
           freerun ? "FREE-RUN (no steering)" : "locking", synth ? " [synthetic reference]" : "", secs, dir);
    fflush(stdout);

    double L = LINE_NS, off = off_us * 1e3;
    int reg = v0, reg_lag = v0, nf = 0, drops = 0, writes = 0, inlock = 0, have_snap = 0;
    int64_t prev_ts = 0, t_print = t0, wr_max = 0;
    uint32_t prev_seq = 0;
    // per-second stats
    double s_sum = 0, s_sq = 0, s_max = 0; int s_n = 0, s_vmin = 1 << 30, s_vmax = 0;
    int64_t t_end = t0 + (int64_t)(secs * 1e9), t_synth = t0 + 1000000000ll;

    while (!stop && nf < nmax && now_ns(CLOCK_MONOTONIC) < t_end) {
        struct pollfd pf[2] = {{.fd = gfd, .events = POLLIN}, {.fd = fd, .events = POLLIN}};
        int pr = poll(pf, 2, 1000);
        if (pr < 0 && errno == EINTR) continue;
        if (pr <= 0) { fprintf(stderr, "no frame for 1 s, stream hung\n"); break; }
        for (; synth && now_ns(CLOCK_MONOTONIC) >= t_synth; t_synth += (int64_t)tp_nom) on_edge(t_synth, tp_nom);
        if (pf[0].revents & POLLIN) {  // edges first, so a frame next to an edge sees it
            struct gpio_v2_line_event ev[16];
            ssize_t r = read(gfd, ev, sizeof ev);
            for (int i = 0; r > 0 && i < (int)(r / sizeof ev[0]); i++) on_edge((int64_t)ev[i].timestamp_ns, tp_nom);
        }
        if (!(pf[1].revents & POLLIN)) continue;
        struct v4l2_buffer b = {.type = rb.type, .memory = rb.memory};
        if (ioctl(fd, VIDIOC_DQBUF, &b) < 0) { if (errno == EINTR || errno == EAGAIN) continue; die("dqbuf"); }
        int64_t ts_abs = b.timestamp.tv_sec * 1000000000ll + b.timestamp.tv_usec * 1000ll;
        uint32_t seq = b.sequence;
        uint16_t *c = cells + (size_t)nf * GX * GY;
        for (int y = 0; y < H; y += ROWSTEP) {  // uncached DMA buffer: copy each row once, then sum
            memcpy(row, map[b.index] + y * bpl, W);
            uint16_t *cr = c + (y / CELL) * GX;
            for (int cx = 0; cx < GX; cx++) {
                unsigned s = 0;
                for (int x = cx * CELL; x < cx * CELL + CELL; x++) s += row[x];
                cr[cx] += s;
            }
        }
        if (!have_snap && nf == (int)fps) {
            for (int y = 0; y < H; y++) memcpy(snap + y * W, map[b.index] + y * bpl, W);
            have_snap = 1;
        }
        if (ioctl(fd, VIDIOC_QBUF, &b) < 0) die("qbuf");

        int gap = nf && seq != prev_seq + 1;
        if (gap) drops += seq - prev_seq - 1;
        int v_a = reg_lag, v_b = reg;  // vblank of intervals (n-1 -> n) and (n -> n+1)
        // Learn the line time from undisturbed intervals.
        if (nf && !gap) {
            double lo = (ts_abs - prev_ts) / (v_a + H + 0.95);
            if (fabs(lo / L - 1) < 3e-4) L += 0.02 * (lo - L);
        }
        frec_t fr = {.seq = seq, .ts = ts_abs, .k = -1, .e_us = NAN, .vb = v_b};
        int ref_ok = nedge >= 4 && ts_abs - last_edge_raw < 3 * tp_hat;
        int v_c = v0;
        if (ref_ok) {
            double T = tp_hat / N, d = (ts_abs - t0) - e_hat - off;
            int64_t m = (int64_t)floor(d / T + 0.5);
            double e = d - m * T;
            fr.k = ek; fr.m = (int32_t)m; fr.e_us = e / 1e3;
            inlock = fabs(e) < LOCK_US * 1e3 ? inlock + 1 : 0;
            fr.locked = inlock >= LOCK_FRAMES;
            // Phase of frame n+1 is already fixed by v_b; choose v_c for n+1 -> n+2.
            double e1 = e + (v_b + H + 0.95) * L - T;
            e1 -= T * floor(e1 / T + 0.5);
            v_c = (int)lround((T - G * e1) / L - H - 0.95);
            if (v_c < vb_min) v_c = vb_min;
            if (v_c > vb_max) v_c = vb_max;
            if (fr.locked) {
                s_sum += e; s_sq += e * e; s_n++;
                if (fabs(e) > s_max) s_max = fabs(e);
            }
        }
        if (freerun) v_c = v0;
        reg_lag = reg;
        if (v_c != reg) {
            int64_t w0 = now_ns(CLOCK_MONOTONIC);
            set_ctrl(sd, V4L2_CID_VBLANK, v_c, "vblank");
            int64_t dw = now_ns(CLOCK_MONOTONIC) - w0;
            if (dw > wr_max) wr_max = dw;
            reg = v_c; writes++;
        }
        if (reg < s_vmin) s_vmin = reg;
        if (reg > s_vmax) s_vmax = reg;
        flog[nf++] = fr;
        prev_ts = ts_abs; prev_seq = seq;

        int64_t tn = now_ns(CLOCK_MONOTONIC);
        if (tn - t_print > 1000000000ll) {
            t_print = tn;
            if (!ref_ok)
                printf("seq %6u  NO REFERENCE (%d edges)  drops %d\n", seq, nelog, drops);
            else if (!s_n)
                printf("seq %6u  acquiring  e %8.1f us  vblank %d  drops %d\n", seq, fr.e_us, reg, drops);
            else {
                double mu = s_sum / s_n, sdv = sqrt(fmax(s_sq / s_n - mu * mu, 0));
                printf("seq %6u  %s  e mean %+6.2f sd %5.2f max %6.2f us  vblank %d..%d  line %+6.1f ppm  "
                       "writes %d (max %.0f us)  drops %d\n",
                       seq, freerun ? "free  " : "LOCKED", mu / 1e3, sdv / 1e3, s_max / 1e3, s_vmin, s_vmax,
                       (L / LINE_NS - 1) * 1e6, writes, wr_max / 1e3, drops);
            }
            fflush(stdout);
            s_sum = s_sq = s_max = 0; s_n = 0; s_vmin = 1 << 30; s_vmax = 0;
        }
    }
    ioctl(fd, VIDIOC_STREAMOFF, &type);

    mkdir(dir, 0755);
    chown_to_caller(dir);
    char path[160];
    snprintf(path, sizeof path, "%s/frames.csv", dir);
    FILE *fp = fopen(path, "w");
    if (!fp) die(path);
    fprintf(fp, "i,seq,ts_ns,k,m,e_us,vblank_next,locked\n");
    for (int i = 0; i < nf; i++)
        fprintf(fp, "%d,%u,%lld,%lld,%d,%.3f,%d,%u\n", i, flog[i].seq, (long long)flog[i].ts, (long long)flog[i].k,
                flog[i].m, flog[i].e_us, flog[i].vb, flog[i].locked);
    fclose(fp); chown_to_caller(path);
    snprintf(path, sizeof path, "%s/edges.csv", dir);
    if (!(fp = fopen(path, "w"))) die(path);
    fprintf(fp, "ts_ns,ts_real_ns,k,est_ns,resid_ns,used\n");
    for (int i = 0; i < nelog; i++)
        fprintf(fp, "%lld,%lld,%lld,%lld,%.0f,%u\n", (long long)elog[i].ts, (long long)(elog[i].ts + real_minus_mono),
                (long long)elog[i].k, (long long)llround(elog[i].est) + t0, elog[i].r, elog[i].used);
    fclose(fp); chown_to_caller(path);
    snprintf(path, sizeof path, "%s/cells.u16", dir);
    if (!(fp = fopen(path, "wb")) || fwrite(cells, (size_t)GX * GY * 2, nf, fp) != (size_t)nf) die(path);
    fclose(fp); chown_to_caller(path);
    snprintf(path, sizeof path, "%s/snap.pgm", dir);
    if (!(fp = fopen(path, "wb"))) die(path);
    fprintf(fp, "P5 %d %d 255\n", W, H);
    fwrite(snap, W * H, 1, fp);
    fclose(fp); chown_to_caller(path);
    snprintf(path, sizeof path, "%s/meta.txt", dir);
    if (!(fp = fopen(path, "w"))) die(path);
    fprintf(fp, "host=%s\nfps=%.6f\npulse_hz=%.6f\nN=%d\nperiod_ns=%.3f\nline_ns=%.4f\nexposure_lines=%d\ngain=%d\n"
                "offset_us=%.3f\nfreerun=%d\ngx=%d\ngy=%d\ncell=%d\nrowstep=%d\nframes=%d\ndrops=%d\nwrites=%d\n",
            host, fps, pulse_hz, N, tp_hat / N, L, expo, gc.value, off_us, freerun, GX, GY, CELL, ROWSTEP, nf, drops, writes);
    fclose(fp); chown_to_caller(path);
    printf("%d frames, %d dropped, %d edges, %d vblank writes -> %s/\n", nf, drops, nelog, writes, dir);
    return 0;
}
