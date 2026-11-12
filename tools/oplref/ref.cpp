// tools/oplref/ref.cpp: plays a register script (tools/oplref/walk.txt, the format of tools/oplref/mkwalk.py) on
// ymfm's YMF262 and writes every chip-rate sample to OUT: the four outputs A, B, C, D, each signed 16-bit
// little-endian (ymf262::generate clamps them). The chip is constructed, then reset, as a host does; a write
// goes through the address port (0, or 2 for 0x100 and up) and then the data port (1, or 3), as on the bus.
//   oplref SCRIPT OUT
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "ymfm_opl.h"

int main(int argc, char **argv)
{
	if (argc != 3) { std::fprintf(stderr, "usage: oplref SCRIPT OUT\n"); return 2; }
	FILE *in = std::fopen(argv[1], "r");
	FILE *out = std::fopen(argv[2], "wb");
	if (!in || !out) { std::fprintf(stderr, "oplref: cannot open %s or %s\n", argv[1], argv[2]); return 2; }
	ymfm::ymfm_interface intf;
	ymfm::ymf262 chip(intf);
	chip.reset();
	char line[256];
	unsigned long samples = 0;
	while (std::fgets(line, sizeof line, in)) {
		unsigned reg, val;
		unsigned long n;
		if (line[0] == 'w' && std::sscanf(line + 1, "%x %x", &reg, &val) == 2) {
			unsigned hi = reg >> 8;
			chip.write(hi ? 2 : 0, uint8_t(reg & 0xff));
			chip.write(hi ? 3 : 1, uint8_t(val));
		} else if (line[0] == 's' && std::sscanf(line + 1, "%lu", &n) == 1) {
			for (unsigned long i = 0; i < n; i++) {
				ymfm::ymf262::output_data o;
				chip.generate(&o, 1);
				unsigned char b[8];
				for (int k = 0; k < 4; k++) {
					uint16_t v = uint16_t(int16_t(o.data[k]));
					b[2 * k] = uint8_t(v & 0xff);
					b[2 * k + 1] = uint8_t(v >> 8);
				}
				std::fwrite(b, 1, sizeof b, out);
			}
			samples += n;
		}
	}
	std::fclose(out);
	std::printf("oplref: samples %lu\n", samples);
	return 0;
}
