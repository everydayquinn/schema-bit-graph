public class Probe {
    private int a;
    private int b;
    private int c;
    private int x;
    private int y;
    private Counter counter;

    public Probe() {
        this.a = 1;
        b = 2;
    }

    public void compoundOps() {
        a += 5;
        this.b -= 3;
        c = c + 1;
    }

    public void shadowParam(int x) {
        x = x + 1;
        this.x = x;
    }

    public void shadowLocal() {
        int x = 5;
        x = x + 1;
        this.x = x;
    }

    public void readsViaQualifier() {
        counter.increment();
        int v = counter.value();
    }

    public void staticReads() {
        Probe.staticThing();
        System.out.println("ok");
    }

    public void mixedRW() {
        a = a + b * c;
        y = this.y * 2;
    }

    public void selfRecurse() {
        selfRecurse();
    }

    public static int staticThing() { return 0; }
}
