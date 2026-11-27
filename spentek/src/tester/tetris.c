/* Tetris for the LPM-10A tester. Runs entirely in the GUI task: t_poll() is called from the
   GUI loop before it waits on its queue; keys arrive from the key task through t_key(). */
typedef unsigned char u8; typedef signed char s8; typedef unsigned short u16; typedef unsigned int u32;

#define DRAW_SHAPE ((void (*)(int, int, int, int, int))0x08016D09)       /* filled rect, inclusive corners */
#define GUI_BLIT   ((void (*)(int, int, int, int, int, const char *))0x080174E9)
#define TICKS      ((u32 (*)(void))0x0801C5B1)
#define FGBG       ((volatile u16 *)0x200001AC)
#define SYS        ((volatile u8 *)0x2000013C)
#define ST         ((volatile u8 *)0x2000FE40)
#define SETTINGS   ((volatile u8 *)0x20000C78)
#define PAGE_TETRIS 3
#define MAGIC 0x7E

struct G {
    u8 magic, over, type, rot;
    s8 x, y; u8 next, redraw;
    u32 due, score;
    u16 lines; u8 level, pad;
    volatile u8 k[8];
    u32 rng;
    u8 board[200];
};
#define g ((struct G *)0x2000F900)

/* Debug log: lives above the zero-initialised RAM, so it survives a reset (not a power loss). */
#define NLOG 24
struct L {
    u32 magic, last_tick, boots;
    u8 head, stage, msg, rst;
    struct { u32 t; u8 c, a; u16 b; } e[NLOG];
};
#define lg ((struct L *)0x2000FA00)
#define LMAGIC 0x4C4F4731
#define RCC_CSR (*(volatile u32 *)0x40021024)
#define RECORD ((volatile u32 *)0x2000F110)
#define SPRINTF ((int (*)(char *, const char *, ...))0x0800A38D)
#define BATT_MV ((u32 (*)(void))0x080108F9)
#define HEAP_FREE (*(volatile u32 *)0x20000200)

void t_log(u32 c, u32 a, u32 b)
{
    struct L *l = lg;
    u32 h = l->head;
    if (h >= NLOG) h = 0;
    l->e[h].t = TICKS(); l->e[h].c = c; l->e[h].a = a; l->e[h].b = b;
    l->head = h + 1 >= NLOG ? 0 : h + 1;
}

static void log_reset(void)
{
    volatile u8 *p = (volatile u8 *)lg;
    for (int i = 0; i < (int)sizeof(struct L); i++) p[i] = 0;
    lg->magic = LMAGIC;
}

void t_clear(void) { u32 b = lg->boots; u8 r = lg->rst; log_reset(); lg->boots = b; lg->rst = r; }

/* GUI task: a message is about to be handled */
void t_msg(u32 id) { lg->msg = id; }

enum { BX = 16, BY = 62, CELL = 12, PX = 146 };
enum { K_LEFT, K_RIGHT, K_ROT, K_DROP, K_OK };
#define BLACK 0x0000
#define WHITE 0xFFFF
#define GREY  0x8410
#define PANEL 0x2105
#define EDGE  0x07FF

static const u16 SH[7][4] = {
    {0x0F00, 0x2222, 0x00F0, 0x4444},   /* I */
    {0x44C0, 0x8E00, 0x6440, 0x0E20},   /* J */
    {0x4460, 0x0E80, 0xC440, 0x2E00},   /* L */
    {0xCC00, 0xCC00, 0xCC00, 0xCC00},   /* O */
    {0x06C0, 0x8C40, 0x6C00, 0x4620},   /* S */
    {0x0E40, 0x4C40, 0x4E00, 0x4640},   /* T */
    {0x0C60, 0x4C80, 0xC600, 0x2640},   /* Z */
};
/* colours chosen to stay distinct after the tester's theme remaps cool colours onto one ramp */
static const u16 COL[8] = {BLACK, 0x07FF, 0x0640, 0xFD20, 0xFFE0, 0x0500, 0xFB14, 0xF800};

static void rect(int x0, int y0, int x1, int y1, int c) { DRAW_SHAPE(x0, y0, x1, y1, c); }

static void text(int x, int y, int size, int fg, int bg, const char *s)
{
    int n = 0;
    while (s[n]) n++;
    FGBG[0] = fg; FGBG[1] = bg;
    GUI_BLIT(x, y, n * (size >> 1), size, size, s);
}

static void number(int x, int y, u32 v)
{
    char b[8];
    int i = 6;
    b[7] = 0;
    do { b[i--] = '0' + v % 10; v /= 10; } while (v && i >= 0);
    while (i >= 0) b[i--] = ' ';
    text(x, y, 16, WHITE, PANEL, b);
}

static void cell(int cx, int cy, int c)
{
    int x = BX + cx * CELL, y = BY + cy * CELL;
    rect(x, y, x + CELL - 2, y + CELL - 2, c);
}

static int bit(int type, int rot, int i) { return (SH[type][rot] >> (15 - i)) & 1; }

static int collide(int type, int rot, int x, int y)
{
    for (int i = 0; i < 16; i++) {
        if (!bit(type, rot, i)) continue;
        int cx = x + (i & 3), cy = y + (i >> 2);
        if (cx < 0 || cx > 9 || cy > 19) return 1;
        if (cy >= 0 && g->board[cy * 10 + cx]) return 1;
    }
    return 0;
}

static void piece(int c)
{
    for (int i = 0; i < 16; i++) {
        if (!bit(g->type, g->rot, i)) continue;
        int cx = g->x + (i & 3), cy = g->y + (i >> 2);
        if (cy >= 0) cell(cx, cy, c);
    }
}

static void preview(void)
{
    rect(PX + 2, 80, PX + 45, 123, BLACK);
    for (int i = 0; i < 16; i++)
        if (bit(g->next, 0, i)) {
            int x = PX + 4 + (i & 3) * 10, y = 82 + (i >> 2) * 10;
            rect(x, y, x + 8, y + 8, COL[g->next + 1]);
        }
}

static void hud(void)
{
    number(PX + 2, 154, g->score);
    number(PX + 2, 198, g->lines);
    number(PX + 2, 242, g->level);
}

static void board(void)
{
    for (int cy = 0; cy < 20; cy++)
        for (int cx = 0; cx < 10; cx++)
            cell(cx, cy, COL[g->board[cy * 10 + cx]]);
}

static void banner(void)
{
    rect(BX + 4, BY + 96, BX + 115, BY + 143, 0xF800);
    text(BX + 24, BY + 102, 16, WHITE, 0xF800, "GAME OVER");
    text(BX + 21, BY + 124, 12, WHITE, 0xF800, "OK = new game");
}

static void draw_all(void)
{
    rect(BX - 2, BY - 2, BX + 10 * CELL, BY + 20 * CELL, EDGE);
    rect(BX - 1, BY - 1, BX + 10 * CELL - 1, BY + 20 * CELL - 1, BLACK);
    board();
    text(PX + 2, 64, 12, GREY, PANEL, "NEXT");
    text(PX + 2, 140, 12, GREY, PANEL, "SCORE");
    text(PX + 2, 184, 12, GREY, PANEL, "LINES");
    text(PX + 2, 228, 12, GREY, PANEL, "LEVEL");
    text(PX + 2, 268, 12, GREY, PANEL, "<> move");
    text(PX + 2, 280, 12, GREY, PANEL, "UP/OK turn");
    text(PX + 2, 292, 12, GREY, PANEL, "DOWN drop");
    preview();
    hud();
    if (g->over) banner(); else piece(COL[g->type + 1]);
}

static u32 rnd(void)
{
    u32 r = g->rng;
    r ^= r << 13; r ^= r >> 17; r ^= r << 5;
    g->rng = r;
    return r;
}

static int pick(int avoid)
{
    int t = rnd() % 7;
    if (t == avoid) t = rnd() % 7;
    return t;
}

static u32 interval(void)
{
    int ms = 650 - 55 * (g->level - 1);
    return ms < 90 ? 90 : ms;
}

static void spawn(void)
{
    g->type = g->next; g->rot = 0; g->x = 3; g->y = 0;
    g->next = pick(g->type);
    preview();
    if (collide(g->type, 0, 3, 0)) { g->over = 1; piece(COL[g->type + 1]); banner(); return; }
    piece(COL[g->type + 1]);
}

static void newgame(void)
{
    for (int i = 0; i < 200; i++) g->board[i] = 0;
    for (int i = 0; i < 8; i++) g->k[i] = 0;
    g->over = 0; g->score = 0; g->lines = 0; g->level = 1;
    g->rng = TICKS() * 2654435761u + 0x9E3779B9u;
    if (!g->rng) g->rng = 1;
    g->next = pick(7);
    g->type = g->next; g->rot = 0; g->x = 3; g->y = 0;
    g->next = pick(g->type);
    g->magic = MAGIC;
    g->redraw = 1;
}

static void lock(void)
{
    static const u16 pts[5] = {0, 100, 300, 500, 800};
    int n = 0;
    for (int i = 0; i < 16; i++) {
        if (!bit(g->type, g->rot, i)) continue;
        int cx = g->x + (i & 3), cy = g->y + (i >> 2);
        if (cy >= 0) g->board[cy * 10 + cx] = g->type + 1;
    }
    for (int cy = 19; cy >= 0; ) {
        int full = 1;
        for (int cx = 0; cx < 10; cx++) if (!g->board[cy * 10 + cx]) { full = 0; break; }
        if (!full) { cy--; continue; }
        for (int i = cy * 10 + 9; i >= 10; i--) g->board[i] = g->board[i - 10];
        for (int i = 0; i < 10; i++) g->board[i] = 0;
        n++;
    }
    t_log('L', n, g->score);
    if (n) {
        g->score += pts[n] * g->level;
        g->lines += n;
        g->level = 1 + g->lines / 10;
        if (g->level > 99) g->level = 99;
        board();
    }
    hud();
    spawn();
}

static int take(int i)
{
    __asm__ volatile("cpsid i");
    int v = g->k[i];
    g->k[i] = 0;
    __asm__ volatile("cpsie i");
    return v > 4 ? 4 : v;
}

static void step(void)
{
    u32 now = TICKS();
    lg->stage = 2;
    if (g->redraw) { g->redraw = 0; draw_all(); g->due = now + interval(); }
    lg->stage = 3;
    int l = take(K_LEFT), r = take(K_RIGHT), ro = take(K_ROT), dr = take(K_DROP), ok = take(K_OK);
    if (g->over) {
        if (ok) { newgame(); g->redraw = 0; draw_all(); g->due = TICKS() + interval(); }
        return;
    }
    ro += ok;
    if (l | r | ro | dr) {
        int x = g->x, y = g->y, rot = g->rot;
        while (ro--) {
            static const s8 kick[5] = {0, -1, 1, -2, 2};
            int nr = (rot + 1) & 3;
            for (int i = 0; i < 5; i++)
                if (!collide(g->type, nr, x + kick[i], y)) { rot = nr; x += kick[i]; break; }
        }
        while (l--) if (!collide(g->type, rot, x - 1, y)) x--;
        while (r--) if (!collide(g->type, rot, x + 1, y)) x++;
        if (dr) while (!collide(g->type, rot, x, y + 1)) { y++; g->score++; }
        if (x != g->x || y != g->y || rot != g->rot) {
            piece(BLACK);
            g->x = x; g->y = y; g->rot = rot;
            piece(COL[g->type + 1]);
        }
        if (dr) { lock(); g->due = TICKS() + interval(); return; }
    }
    lg->stage = 4;
    if ((int)(now - g->due) >= 0) {
        if (!collide(g->type, g->rot, g->x, g->y + 1)) {
            piece(BLACK); g->y++; piece(COL[g->type + 1]);
        } else lock();
        g->due = now + interval();
    }
}

/* GUI loop: returns the queue timeout (ticks) the loop should use */
u32 t_poll(u32 timeout)
{
    struct L *l = lg;
    u32 now = TICKS();
    if (l->magic != LMAGIC) log_reset();
    if (now < l->last_tick || !l->boots) {                  /* the clock went back: this is a new boot */
        u32 csr = RCC_CSR;
        l->boots++;
        l->rst = csr >> 24;
        t_log('B', l->rst, (l->stage << 8) | l->msg);       /* what the GUI task was doing when it stopped */
        g->magic = 0;                                       /* a paused game does not survive a restart */
        RCC_CSR = csr | (1u << 24);                         /* clear the reset flags for next time */
    }
    l->last_tick = now;
    if (SETTINGS[0xA5] != 1) SETTINGS[0xA5] = 1;            /* English only: the second language is gone from the UI */
    if (SETTINGS[0xA8]) SETTINGS[0xA8] = 0;                 /* and so is the first-boot language picker */
    l->msg = 0; l->stage = 0;
    if (SYS[0] != 11 || SYS[3] != 1 || ST[0] != PAGE_TETRIS) {
        return timeout;                                     /* not showing: the game stays paused in memory */
    }
    if (g->magic != MAGIC) return timeout;                  /* page not drawn yet */
    if (((int (*)(void))0x0800E40D)()) return timeout;      /* low-battery warning owns the screen */
    u16 fg = FGBG[0], bg = FGBG[1];
    l->stage = 1;
    step();
    l->stage = 0;
    FGBG[0] = fg; FGBG[1] = bg;
    return timeout > 20 ? 20 : timeout;
}

/* key task */
void t_key(u32 k)
{
    if (k > 4 || g->magic != MAGIC) return;
    __asm__ volatile("cpsid i");
    if (g->k[k] < 250) g->k[k]++;
    __asm__ volatile("cpsie i");
}

/* GUI task: the Tetris page was (re)drawn */
void t_enter(void)
{
    int resume = g->magic == MAGIC && !g->over && g->type < 7 && g->rot < 4;
    if (!resume) newgame();
    for (int i = 0; i < 8; i++) g->k[i] = 0;
    g->redraw = 1;
    t_log('E', resume, g->lines);
}

/* GUI task: draw the Debug page's live lines */
void t_debug(void)
{
    struct L *l = lg;
    char b[48];
    u8 r = l->rst;
    int y = 84;
    SPRINTF(b, "boots %d  reset %02X %s%s%s%s   ", l->boots, r, r & 0x20 ? "WDG " : "", r & 0x10 ? "SOFT " : "",
            r & 0x08 ? "POR " : "", r & 0x04 ? "PIN" : "");
    text(12, y, 12, WHITE, PANEL, b); y += 14;
    if (RECORD[0] == 0xDEADBEEF && RECORD[1] == 0x21524110) {
        SPRINTF(b, "FAULT PC %08X LR %08X", RECORD[2], RECORD[3]);
        text(12, y, 12, 0xF800, PANEL, b); y += 14;
        SPRINTF(b, "CFSR %08X SP %08X IRQ %d ", RECORD[4], RECORD[7], RECORD[8]);
        text(12, y, 12, 0xF800, PANEL, b); y += 14;
    } else {
        text(12, y, 12, WHITE, PANEL, "no fault recorded                 "); y += 28;
    }
    SPRINTF(b, "heap %d  up %ds  %dmV   ", HEAP_FREE, TICKS() / 1000, BATT_MV());
    text(12, y, 12, WHITE, PANEL, b); y += 18;
    int h = l->head;
    for (int i = 0; i < 11; i++) {
        h = h ? h - 1 : NLOG - 1;
        if (!l->e[h].c) { text(12, y, 12, GREY, PANEL, "                           "); y += 13; continue; }
        SPRINTF(b, "%6d.%ds ? %02X %04X   ", l->e[h].t / 1000, (l->e[h].t / 100) % 10, l->e[h].a, l->e[h].b);
        for (int k = 0; b[k]; k++) if (b[k] == '?') { b[k] = l->e[h].c; break; }
        text(12, y, 12, l->e[h].c == 'B' ? 0xFFE0 : WHITE, PANEL, b); y += 13;
    }
}
