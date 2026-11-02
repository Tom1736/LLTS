// Moving-ROI test: stream 1280x800 GREY, crop the OV9281 window over I2C,
// then jump the window between two rows and see which frame shows the jump.
// usage: roi_test H vts yA yB [frames] [period] [width]
#define _GNU_SOURCE
#include <fcntl.h>
#include <linux/i2c-dev.h>
#include <linux/videodev2.h>
#include <math.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define W 1280
#define NBUF 4
#define MAXF 20000

static int i2c, xe = 0x50f;

static double now_ms(void)
{
	struct timespec t;
	clock_gettime(CLOCK_MONOTONIC, &t);
	return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}

static void wr(uint16_t reg, const uint8_t *d, int n)
{
	uint8_t b[16] = { reg >> 8, reg & 0xff };
	memcpy(b + 2, d, n);
	if (write(i2c, b, n + 2) != n + 2)
		perror("i2c write");
}

static void wr16(uint16_t reg, int v)
{
	uint8_t d[2] = { v >> 8, v & 0xff };
	wr(reg, d, 2);
}

// Y_START (0x3802), X_END (0x3804, unchanged), Y_END (0x3806) in one burst.
static void set_y(int y0, int h)
{
	int ye = y0 + h + 15;
	uint8_t d[6] = { y0 >> 8, y0 & 0xff, xe >> 8, xe & 0xff, ye >> 8, ye & 0xff };
	wr(0x3802, d, 6);
}

int main(int argc, char **argv)
{
	int h = atoi(argv[1]), vts = atoi(argv[2]), ya = atoi(argv[3]), yb = atoi(argv[4]);
	int nf = argc > 5 ? atoi(argv[5]) : 3000, period = argc > 6 ? atoi(argv[6]) : 20;
	int wd = argc > 7 ? atoi(argv[7]) : W, x0 = 640 - wd / 2;

	struct sched_param sp = { .sched_priority = 80 };
	if (sched_setscheduler(0, SCHED_FIFO, &sp))
		perror("SCHED_FIFO (run with sudo)");

	i2c = open("/dev/i2c-10", O_RDWR);
	if (i2c < 0 || ioctl(i2c, I2C_SLAVE_FORCE, 0x60)) {
		perror("i2c");
		return 1;
	}
	int fd = open("/dev/video0", O_RDWR);
	struct v4l2_requestbuffers rb = { .count = NBUF, .type = V4L2_BUF_TYPE_VIDEO_CAPTURE, .memory = V4L2_MEMORY_MMAP };
	if (ioctl(fd, VIDIOC_REQBUFS, &rb)) {
		perror("REQBUFS");
		return 1;
	}
	uint8_t *mem[NBUF];
	for (int i = 0; i < NBUF; i++) {
		struct v4l2_buffer b = { .type = rb.type, .memory = rb.memory, .index = i };
		ioctl(fd, VIDIOC_QUERYBUF, &b);
		mem[i] = mmap(NULL, b.length, PROT_READ, MAP_SHARED, fd, b.m.offset);
		ioctl(fd, VIDIOC_QBUF, &b);
	}
	int type = rb.type;
	ioctl(fd, VIDIOC_STREAMON, &type);

	static double ts[MAXF], dq[MAXF], mean[MAXF], wdur[MAXF], tcopy[MAXF], tproc[MAXF];
	static int seq[MAXF], want[MAXF];
	int cur = ya;
	for (int k = 0; k < nf && k < MAXF; k++) {
		struct v4l2_buffer b = { .type = rb.type, .memory = rb.memory };
		if (ioctl(fd, VIDIOC_DQBUF, &b)) {
			perror("DQBUF");
			break;
		}
		dq[k] = now_ms();
		ts[k] = b.timestamp.tv_sec * 1e3 + b.timestamp.tv_usec / 1e3;
		seq[k] = b.sequence;
		// copy the valid crop rows out of the (uncached) DMA buffer, then process the copy
		static uint8_t img[W * 800];
		int rows = k < 30 ? 800 : h, cols = k < 30 ? W : wd;
		double c0 = now_ms();
		for (int r = 0; r < rows; r++)
			memcpy(img + r * cols, mem[b.index] + r * W, cols);
		double c1 = now_ms();
		long sum = 0;
		for (int i = 0; i < rows * cols; i++)
			sum += img[i];
		mean[k] = sum / (double)(rows * cols);
		tcopy[k] = c1 - c0;
		tproc[k] = now_ms() - c1;
		ioctl(fd, VIDIOC_QBUF, &b);

		want[k] = -1;
		if (k == 20) { // switch to cropped window
			xe = x0 + wd + 15;
			wr16(0x3800, x0);
			wr16(0x3808, wd);
			set_y(cur, h);
			wr16(0x380a, h);
			wr16(0x380e, vts);
		} else if (k > 100 && k % period == 0) { // jump ROI right after this frame
			cur = cur == ya ? yb : ya;
			double t0 = now_ms();
			set_y(cur, h);
			wdur[k] = now_ms() - t0;
			want[k] = cur;
		}
	}
	type = rb.type;
	ioctl(fd, VIDIOC_STREAMOFF, &type);

	// summary
	int n = nf, gaps = 0;
	double lat_sum = 0, lat_max = 0, wsum = 0;
	for (int k = 120; k < n; k++) {
		gaps += seq[k] - seq[k - 1] - 1;
		double l = dq[k] - ts[k];
		lat_sum += l;
		if (l > lat_max)
			lat_max = l;
	}
	double frame = (ts[n - 1] - ts[120]) / (seq[n - 1] - seq[120]);
	printf("H=%d vts=%d: frame %.4f ms (%.1f fps), seq gaps %d\n", h, vts, frame, 1000 / frame, gaps);
	printf("ts->userspace: mean %.3f ms, max %.3f ms\n", lat_sum / (n - 120), lat_max);
	double tc = 0, tp = 0;
	for (int k = 120; k < n; k++) {
		tc += tcopy[k];
		tp += tproc[k];
	}
	tc /= n - 120;
	tp /= n - 120;
	printf("copy %d KB: %.3f ms (%.0f MB/s), process copy: %.3f ms\n", h * wd / 1024, tc, h * wd / tc / 1e3, tp);

	// which frame after the write shows the jump? compare against the two levels
	int hist[6] = { 0 }, cnt = 0;
	double ma = 0, mb = 0;
	int na = 0, nb = 0;
	for (int k = 120; k < n; k++)
		if (want[k] >= 0 && k + 5 < n) { // frames k+3..k+5 show the new window for sure
			double m = (mean[k + 3] + mean[k + 4] + mean[k + 5]) / 3;
			if (want[k] == ya) { ma += m; na++; } else { mb += m; nb++; }
		}
	ma /= na; mb /= nb;
	printf("crop mean at yA=%d: %.2f, at yB=%d: %.2f\n", ya, ma, yb, mb);
	for (int k = 120; k < n; k++)
		if (want[k] >= 0 && k + 5 < n) {
			double target = want[k] == ya ? ma : mb, other = want[k] == ya ? mb : ma;
			for (int j = 0; j <= 5; j++)
				if (fabs(mean[k + j] - target) < fabs(mean[k + j] - other)) {
					hist[j]++;
					break;
				}
			wsum += wdur[k];
			cnt++;
		}
	printf("I2C write (8 bytes) mean %.3f ms over %d jumps\n", wsum / cnt, cnt);
	printf("first frame with new ROI after write following frame k: ");
	for (int j = 0; j <= 5; j++)
		printf("k+%d:%d ", j, hist[j]);
	printf("\n");
	return 0;
}
