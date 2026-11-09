#!/bin/sh
set -eu

workspace=${WORKSPACE:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}
toolchain=${TOOLCHAIN_PREFIX:-"$workspace/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"}
qdrv_ko=${1:-"$workspace/work/linux510-radio-port/quantenna/qdrv/qdrv.ko"}
oem_modules=${2:-"$workspace/work/hgw500-rootfs-live/squashfs-root/lib/modules/2.6.35.12"}
vmlinux=${3:-"/home/user/openmitrastar-build/engineering/vmlinux"}
output=${4:-"$workspace/outputs/kernel-port/qdrv-linux510-symbol-owners.tsv"}

nm="${toolchain}nm"
readelf="${toolchain}readelf"

for required in "$qdrv_ko" "$oem_modules" "$vmlinux"; do
	if [ ! -e "$required" ]; then
		echo "missing input: $required" >&2
		exit 1
	fi
done

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

"$nm" -u "$qdrv_ko" | awk 'NF { print $NF }' | sort -u > "$tmp/undefined"

"$nm" --defined-only "$vmlinux" |
	awk '$3 ~ /^__ksymtab_.+/ {
		sub(/^__ksymtab_/, "", $3)
		print $3 "\tkernel-5.10-export"
	}' > "$tmp/providers"

find "$oem_modules" -type f -name '*.ko' -print |
while IFS= read -r module; do
	provider=${module#"$oem_modules"/}
	"$readelf" -rW "$module" 2>/dev/null |
		awk -v provider="$provider" '
			/Relocation section .*\.rela__ksymtab/ { in_ksymtab = 1; next }
			/^Relocation section/ { in_ksymtab = 0 }
			in_ksymtab && $1 ~ /^[[:xdigit:]]+$/ && $5 != "__ksymtab_strings" {
				print $5 "\toem:" provider
			}
		' >> "$tmp/providers"
done

sort -u -k1,1 -k2,2 "$tmp/providers" -o "$tmp/providers"

{
	printf 'symbol\tproviders\n'
	awk -F '\t' '
		NR == FNR {
			providers[$1] = providers[$1] ? providers[$1] "," $2 : $2
			next
		}
		{
			print $1 "\t" (providers[$1] ? providers[$1] : "unresolved")
		}
	' "$tmp/providers" "$tmp/undefined"
} > "$output"

total=$(wc -l < "$tmp/undefined" | tr -d ' ')
kernel=$(awk -F '\t' '$2 ~ /kernel-5.10-export/ { n++ } END { print n + 0 }' "$output")
oem=$(awk -F '\t' '$2 ~ /oem:/ { n++ } END { print n + 0 }' "$output")
unresolved=$(awk -F '\t' '$2 == "unresolved" { n++ } END { print n + 0 }' "$output")

printf 'qdrv undefined symbols: %s\n' "$total"
printf 'provided by Linux 5.10 exports: %s\n' "$kernel"
printf 'provided by at least one OEM module: %s\n' "$oem"
printf 'not found in either export set: %s\n' "$unresolved"
printf 'matrix: %s\n' "$output"
