set -eu
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic /workspace/user-home/Desktop/MitraStar/work/kernel-port/f344/f344_transaction.c /workspace/user-home/Desktop/MitraStar/work/kernel-port/f344/test_transaction.c -o /tmp/f344-transaction-test
/tmp/f344-transaction-test
