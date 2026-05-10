public class Edge {
    private int counter;
    private int n;

    // Two definitions named "value" exist (here and Counter.value); the
    // ambiguity policy should skip CALLED_BY for unresolved ambiguous calls.
    public int value() {
        return this.counter;
    }

    public void usesValue() {
        Counter c = new Counter();
        c.value();        // simple-name 'value' is ambiguous → no CALLED_BY edge
    }

    public void postfixField() {
        n++;              // bare postfix: WRITE+READ n
        ++n;              // bare prefix:  WRITE+READ n
        this.n++;         // this-postfix: WRITE+READ n
        --this.n;         // this-prefix:  WRITE+READ n
    }

    public void usedThenDeclared() {
        // Pre-pass sweeps the whole body; declaring `int counter` ANYWHERE
        // in the body should shadow the field everywhere in the method.
        counter = 99;     // expected: NO field write (local shadows)
        int counter = 7;
    }
}
