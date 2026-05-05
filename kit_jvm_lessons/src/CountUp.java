/**
 * CountUp — calibration program for parser_jvm traveler.
 *
 * countTo(n) sums 0+1+...+(n-1). countTo(5) = 10.
 *
 * The countTo() method exercises exactly the 7 JVM opcodes the parser_jvm
 * traveler is designed to handle:
 *   iconst_*   — PUSHES_STACK
 *   istore_*   — POPS_STACK + WRITES_LOCAL
 *   iload_*    — READS_LOCAL + PUSHES_STACK
 *   iadd       — 2× POPS_STACK + PUSHES_STACK
 *   if_icmpge  — 2× POPS_STACK + BRANCH (conditional)
 *   goto       — BRANCH (unconditional)
 *   ireturn    — POPS_STACK + return-with-value
 *
 * Hand-computable expected fact counts are encoded in test_corkboard.py.
 */
public class CountUp {
    public static int countTo(int n) {
        int sum = 0;
        int i = 0;
        while (i < n) {
            sum = sum + i;
            i = i + 1;
        }
        return sum;
    }

    public static void main(String[] args) {
        System.out.println(countTo(5));
    }
}
