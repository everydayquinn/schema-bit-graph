public class Patterns {
    private int x;
    private int y;
    private boolean flag;

    // ---- getter positive controls (must be IS_GETTER_OF) ----
    public int getX()        { return this.x; }      // this-form, plain
    public int getY()        { return y; }           // bare-form, plain
    public boolean getFlag() { return this.flag; }   // bool variant

    // ---- getter negatives (must NOT be IS_GETTER_OF after fix) ----
    public int negX()        { return -this.x; }     // prefix '-' on This
    public boolean notFlag() { return !this.flag; }  // the Player.isDead shape
    public int negY()        { return -y; }          // prefix '-' on bare ref

    // ---- setter positive control (must be IS_SETTER_OF) ----
    public void setX(int v)    { this.x = v; }

    // ---- setter negative (must NOT be IS_SETTER_OF after fix) ----
    public void setNegX(int v) { this.x = -v; }      // RHS prefix '-' on param
}
