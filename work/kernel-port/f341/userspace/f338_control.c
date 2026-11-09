#include <stdio.h>
#include <unistd.h>
#include <sys/resource.h>
int main(void)
{
 struct rlimit cpu={1,2};
 if(setrlimit(RLIMIT_CPU,&cpu))return 11;
 alarm(3);
 if(getpid()<=0)return 12;
 puts("F338_CONTROL_PASS alarm_seconds=3 cpu_hard_seconds=2 hardware=0");
 return 0;
}
