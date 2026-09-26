/* hello.c: the smallest program worth teaching.
   It adds two numbers and prints the total. */
#include <stdio.h>

static int add(int a, int b)
{
    return a + b;
}

int main(void)
{
    int total = add(2, 3);
    printf("%d\n", total);
    return 0;
}
