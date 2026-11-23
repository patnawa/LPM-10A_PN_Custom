/* LPM-10A probe ("wand"): sound, lamp and key extras on top of PN1.30.
   helper() runs in the 40 kHz timer interrupt; key_release() in the 1 ms one (which pre-empts it),
   so key_release only leaves a request for helper's housekeeping to carry out. */
typedef unsigned char u8; typedef unsigned short u16; typedef unsigned int u32;

#define MS        (*(volatile u32 *)0x200000FC)
#define TICK40    (*(volatile u32 *)0x20000100)
#define MODE      (*(volatile u8 *)0x20000048)       /* 0 digital, 1 analog, 2 mains */
#define PENDING   (*(volatile u8 *)0x20000049)       /* mode + 1 asked for; the main loop applies it */
#define NO_LEDS   (*(volatile u8 *)0x20000054)
#define KEEP      (*(volatile u8 *)0x2000010C)       /* ms left in the current stock beep */
#define GAP       (*(volatile u8 *)0x2000005A)       /* pause after the current tracing pulse: 20 strong .. 146 weak */
#define HOLD      ((volatile u16 *)0x2000010E)       /* 5 ms scans held: mode key, mains key, lamp key */
#define BATT      ((volatile u16 *)0x2000004A)
#define LAMP_ON   (*(volatile u32 *)0x40010818 = 0x400)
#define LAMP_OFF  (*(volatile u32 *)0x40010828 = 0x400)
#define SET_CCR   ((void (*)(u32))0x0800B365)        /* speaker PWM duty, 800 = rest */
#define DELAY     ((void (*)(u32))0x0800B9A1)
#define FL_UNLOCK ((void (*)(void))0x08007BA9)
#define FL_ERASE  ((u32 (*)(u32))0x080079D9)          /* erase the page holding this address */
#define FL_WORD   ((u32 (*)(u32, u32))0x08007AF9)     /* program one word */
#define FL_LOCK   ((void (*)(void))0x08007AE5)
#define SAVED     ((volatile u32 *)0x0801E800)        /* own flash page, below the firmware's version page */
#define SAVE_TAG  0x53504B31u                         /* "SPK1" */
#define OLD       0x0800CE29u                        /* PN1.30's own sound helper */
#define END       0x0800AC7Du

enum { TRACE = 30, LONG = 150, XLONG = 500 };
enum { K_MODE, K_MAINS, K_LAMP };

struct S {
    u8 prevk, start, parity, off;
    u8 lmode, vol, theme, peak_on;
    u8 peak, armed, ph, mute;
    u8 lvl[3], lastmode;
    u8 req, accent, batt_done, seq_div;
    const u8 *seq;
    u32 note_end, t_pulse, t_act, next_batt, save_at, t_sig, t_switch;
    u8 autom, hush, locked, swallow;
    u32 lost_at;
};
#define st ((struct S *)0x20001800)

/* note lists: {ticks between speaker flips (0 = rest), length in 10 ms}, ended by a zero length */
static const u8 TUNE[]  = {19, 9, 15, 9, 13, 9, 10, 18, 0, 4, 13, 7, 10, 14, 0, 0};
static const u8 BLIP1[] = {12, 6, 0, 0};
static const u8 BLIP2[] = {12, 6, 0, 7, 12, 6, 0, 0};
static const u8 BLIP3[] = {12, 6, 0, 7, 12, 6, 0, 7, 12, 6, 0, 0};
static const u8 BLIP4[] = {12, 6, 0, 7, 12, 6, 0, 7, 12, 6, 0, 7, 12, 6, 0, 0};
static const u8 *const BLIPS[4] = {BLIP1, BLIP2, BLIP3, BLIP4};
static const u8 LOST[]  = {8, 9, 11, 9, 15, 9, 21, 16, 0, 0};
static const u8 LOWB[]  = {22, 6, 0, 6, 22, 6, 0, 0};
static const u8 IDLE[]  = {7, 4, 0, 0};
static const u8 HOLD1[] = {9, 3, 0, 0};
static const u8 HOLD2[] = {9, 3, 0, 4, 9, 3, 0, 0};
static const u8 VOLS[]  = {10, 14, 0, 0};
static const u8 TH0[]   = {16, 3, 13, 3, 10, 3, 8, 3, 6, 4, 0, 0};
static const u8 TH1[]   = {8, 12, 0, 0};
static const u8 TH2[]   = {5, 1, 0, 6, 5, 1, 0, 6, 5, 1, 0, 0};
static const u8 TH3[]   = {9, 7, 0, 0};
static const u8 TH4[]   = {4, 1, 6, 1, 9, 1, 13, 1, 18, 1, 0, 0};
static const u8 TH5[]   = {18, 1, 13, 1, 9, 1, 6, 1, 4, 1, 0, 0};
static const u8 TH6[]   = {8, 3, 12, 3, 0, 0};
static const u8 TH7[]   = {7, 1, 10, 1, 7, 1, 10, 1, 7, 1, 10, 1, 0, 0};
static const u8 TH8[]   = {5, 3, 9, 3, 15, 3, 0, 0};
static const u8 TH9[]   = {28, 4, 0, 8, 22, 4, 0, 0};
static const u8 TH10[]  = {5, 1, 0, 1, 5, 1, 0, 1, 5, 1, 0, 0};
static const u8 TH11[]  = {8, 1, 0, 6, 8, 3, 0, 0};
static const u8 TH12[]  = {19, 1, 15, 1, 13, 1, 0, 0};
static const u8 TH13[]  = {7, 3, 0, 5, 10, 3, 0, 0};
/* 0 waka sweep, 1 plain beeps, 2 Geiger click, 3 sonar ping, 4 laser, 5 rise, 6 two-tone, 7 trill,
   8 metal detector, 9 heartbeat, 10 cricket, 11 telegraph, 12 arpeggio, 13 siren */
enum { NTHEME = 14 };
static const u8 *const THS[NTHEME] = {TH0, TH1, TH2, TH3, TH4, TH5, TH6, TH7, TH8, TH9, TH10, TH11, TH12, TH13};
static const u8 PKON[]  = {15, 7, 10, 9, 0, 0};
static const u8 PKOFF[] = {10, 7, 15, 9, 0, 0};
static const u8 AUTON[] = {19, 5, 13, 5, 8, 9, 0, 0};
static const u8 AUTOFF[] = {8, 5, 13, 5, 19, 9, 0, 0};
static const u8 LOCKED[] = {14, 6, 0, 3, 14, 6, 0, 3, 24, 14, 0, 0};
static const u8 UNLOCK[] = {24, 6, 0, 3, 24, 6, 0, 3, 14, 14, 0, 0};
static const u8 DENY[]   = {26, 5, 0, 0};
static const u16 AMP[3] = {300, 110, 40};

static void play(struct S *s, const u8 *p, u32 t)
{
    s->seq = p; s->seq_div = p[0]; s->note_end = t + p[1] * 400u;
}

static void flipa(struct S *s, u32 a)
{
    s->ph ^= 1;
    SET_CCR(s->ph & 1 ? 800 + a : 800 - a);
}

static void flip(struct S *s) { flipa(s, AMP[s->vol]); }

static u32 millivolts(void)
{
    u32 a = BATT[0] + BATT[1] + BATT[2] + BATT[3] + BATT[4];
    return a * 1320 >> 12;                           /* mean of five * 6600 / 4096 */
}

static u32 packed(struct S *s) { return s->vol | s->theme << 8 | (s->lmode == 3 ? 0 : s->lmode) << 16 | s->autom << 24; }

static void set_mode(struct S *s, u32 m)             /* what the mode key does, without its beep */
{
    PENDING = m + 1;
    if (NO_LEDS != 1) {
        *(volatile u32 *)0x40010C18 = 0x8000;
        if (m == 1) *(volatile u32 *)0x40010828 = 0x100;
    }
    s->hush = 1;
}

static void save(struct S *s)                        /* about 30 ms with the processor stalled: only when idle */
{
    u32 v = packed(s);
    if (SAVED[0] == SAVE_TAG && SAVED[1] == v) return;
    FL_UNLOCK();
    if (FL_ERASE((u32)SAVED) == 6 && FL_WORD((u32)SAVED, SAVE_TAG) == 6) FL_WORD((u32)SAVED + 4, v);
    FL_LOCK();
}

static void house(struct S *s, u32 t)                /* every 1.6 ms */
{
    u32 ms = MS, quiet = s->lmode == 2;
    if (HOLD[K_MODE] >= 200 && HOLD[K_LAMP] >= 200) {    /* Mode + Lamp held together for a second: key lock */
        if (s->swallow != 5) { s->swallow = 5; s->locked ^= 1; play(s, s->locked ? LOCKED : UNLOCK, t); }
    } else if (!s->locked && !s->swallow) {
        for (int i = 0; i < 3; i++) {                /* a key being held reaches the long / extra-long mark */
            u32 h = HOLD[i], lv = h >= XLONG ? 2 : h >= LONG ? 1 : 0;
            if (i == K_MODE && h >= XLONG + 200) lv = 2 + (h - XLONG) / 200;   /* still held: one theme a second */
            if (lv > 250) lv = 250;
            if (lv > s->lvl[i]) {
                s->lvl[i] = lv;
                if (lv > 2) {
                    s->theme = s->theme >= NTHEME - 1 ? 0 : s->theme + 1;
                    s->save_at = ms + 3000; play(s, THS[s->theme], t);
                } else play(s, lv == 2 ? HOLD2 : HOLD1, t);
            }
        }
    }
    u32 r = s->req;
    if (r) {
        s->req = 0; s->t_act = t;
        if (r == 8) play(s, DENY, t);                /* a key was pressed while locked */
        else if (r != 4) s->save_at = ms + 3000;         /* volume, theme and lamp mode are kept across power-off */
        if (r == 2) { s->vol = s->vol >= 2 ? 0 : s->vol + 1; play(s, VOLS, t); }
        else if (r == 3) { s->theme = s->theme >= NTHEME - 1 ? 0 : s->theme + 1; play(s, THS[s->theme], t); }
        else if (r == 5) { s->autom ^= 1; s->t_switch = t; s->lost_at = 0; play(s, s->autom ? AUTON : AUTOFF, t); }
        else if (r == 4) { s->peak_on ^= 1; s->peak = 8; s->mute = 0; play(s, s->peak_on ? PKON : PKOFF, t); }
        else if (r == 6) { s->lmode = (s->lmode + 1) & 3; if (!s->lmode) LAMP_OFF; play(s, BLIPS[s->lmode], t); }
    }
    u32 m = MODE;
    if (m != s->lastmode) {                          /* mode announce: 1, 2 or 3 blips */
        s->lastmode = m; s->armed = 0;
        if (s->hush) s->hush = 0;                    /* the probe switched by itself while searching: no blips */
        else { s->t_act = t; if (ms > 1500 && m < 3) play(s, BLIPS[m], t); }
    }
    if (s->autom && m < 2 && !PENDING && !s->seq && ms > 2500     /* auto: no tone heard for 1.2 s, try the other mode */
        && t - s->t_sig > 48000 && t - s->t_switch > 40000) {
        s->t_switch = t;
        set_mode(s, m ^ 1);
    }
    if (s->lmode == 3) { if ((ms / 50) & 1) LAMP_ON; else LAMP_OFF; }      /* strobe, 10 Hz */
    else if (s->lmode) {                             /* lamp follows the tracing pulses */
        if (s->start == TRACE && KEEP && !s->mute) LAMP_ON; else LAMP_OFF;
    }
    if (s->armed >= 3 && t - s->t_pulse > 12000) {   /* a strong signal went quiet for 0.3 s */
        s->armed = 0;
        if (s->autom && m < 2 && !PENDING) {         /* auto: look in the other mode first, alarm only if it is not there */
            s->lost_at = t | 1; s->t_switch = t;
            set_mode(s, m ^ 1);
        } else if (!quiet) play(s, LOST, t);
    }
    if (s->lost_at && (int)(t - s->lost_at) > 52000) {      /* 1.3 s in the other mode and still nothing */
        s->lost_at = 0;
        if (!quiet) play(s, LOST, t);
    }
    if (!s->batt_done) {
        if (ms >= 1300) {                            /* battery level once after the power-on tune: 1..4 blips */
            u32 mv = millivolts();
            s->batt_done = 1; s->next_batt = ms + 60000;
            play(s, BLIPS[mv >= 4000 ? 3 : mv >= 3850 ? 2 : mv >= 3700 ? 1 : 0], t);
        }
    } else if ((int)(ms - s->next_batt) >= 0) {      /* low battery: a low double blip every minute */
        s->next_batt = ms + 60000;
        if (millivolts() < 3600 && !quiet && !s->seq && !KEEP) play(s, LOWB, t);
    }
    if (s->save_at && (int)(ms - s->save_at) >= 0 && !s->seq && !KEEP) { s->save_at = 0; save(s); }
    if (t - s->t_act > 180u * 40000) {               /* on and idle for 3 minutes: a reminder chirp */
        s->t_act = t;
        if (!quiet && !s->seq) play(s, IDLE, t);
    }
}

u32 helper(u32 t)
{
    struct S *s = st;
    if (!(t & 63)) house(s, t);
    if (s->seq) {
        if ((int)(t - s->note_end) >= 0) {
            const u8 *p = s->seq + 2;
            if (p[1]) play(s, p, t);
            else { s->seq = 0; s->prevk = 0; KEEP = 0; SET_CCR(800); return END; }
        }
        if (s->seq_div) { if (t % s->seq_div == 0) flip(s); }
        else if (!(t & 7)) SET_CCR(800);
        return END;
    }
    u32 k = KEEP, mode = MODE, pk = s->prevk, n, amp = AMP[s->vol];
    s->prevk = k;
    if (k > pk && mode != 2) {
        s->start = k;
        if (k == 100 && GAP == 160) { s->t_sig = t; s->lost_at = 0; }    /* the weakest analog level beeps 100 ms with a 160 ms pause */
        if (k == TRACE) {                            /* a tracing pulse begins: the pause after it tells the strength */
            u32 g = GAP, off = g > 20 ? (g - 20) * 58 >> 10 : 0;
            if (off > 7) off = 7;
            s->off = off; s->parity ^= 1; s->t_pulse = t; s->t_act = t; s->t_sig = t; s->lost_at = 0;
            if (off <= 3) { if (s->armed < 3) s->armed++; } else s->armed = 0;
            s->accent = 0; s->mute = 0;
            if (s->peak_on) {
                if (off < s->peak) { s->peak = off; s->accent = 1; }
                else if (off > s->peak + 1u) s->mute = 1;
            }
        }
    }
    if (!k) return OLD;                              /* silence: PN1.30 runs its pulse scheduler here */
    if (mode == 2) n = 4;
    else if (s->start != TRACE) n = ((mode == 1) ^ (k > 50)) ? 16 : 8;   /* key and power beeps as PN1.30 */
    else if (s->lmode == 2 || s->mute) n = 0;
    else if (s->accent) n = 5;                       /* a new strongest reading in peak hold */
    else if (s->theme == 1) n = mode ? 16 : 8;
    else if (s->theme == 2) n = k >= 28 ? 5 : 0;
    else if (s->theme == 3) { n = 9 + s->off; amp = amp * k / 30; }             /* sonar: one pitch, fading out */
    else if (s->theme == 4) n = 4 + ((30 - k) >> 1) + s->off;                   /* laser: fast falling sweep */
    else if (s->theme == 5) n = 4 + (k >> 1) + s->off;                          /* rise: fast rising sweep */
    else if (s->theme == 6) n = (k > 15 ? 8 : 12) + s->off;                     /* two-tone: high then low */
    else if (s->theme == 7) n = (k & 2 ? 7 : 10) + s->off;                      /* trill: two pitches swapping every 2 ms */
    else if (s->theme == 8) n = 5 + 2 * s->off;                                 /* metal detector: steady tone, pitch is the strength */
    else if (s->theme == 9) n = s->parity & 1 ? 22 : 28;                        /* heartbeat: two low thumps in turn */
    else if (s->theme == 10) n = (30 - k) % 10 < 4 ? 5 + s->off : 0;            /* cricket: three short chirps */
    else if (s->theme == 11) n = (s->parity & 1) || k > 20 ? 8 + s->off : 0;    /* telegraph: dot, dash, dot, dash */
    else if (s->theme == 12) n = (k > 20 ? 19 : k > 10 ? 15 : 13) + s->off;     /* arpeggio: three rising notes */
    else if (s->theme == 13) n = (s->parity & 1 ? 7 : 10) + s->off;             /* siren: high and low pulses in turn */
    else {
        u32 v = mode ? k >> 1 : k / 3;
        n = mode ? (s->parity & 1 ? 25 - v : 10 + v) : (s->parity & 1 ? 16 - v : 6 + v);
        n += s->off;
    }
    if (!n) { if (!(t & 7)) SET_CCR(800); }
    else if (t % n == 0) flipa(s, amp);
    return END;
}

/* 1 ms interrupt, a key was released after `held` scans: 1 = let PN1.30 act on it, 0 = handled here */
u32 key_release(u32 key, u32 held)
{
    struct S *s = st;
    if (held < 6) return 0;
    s->t_act = TICK40;
    u32 lv = s->lvl[key];
    s->lvl[key] = 0;
    if (s->swallow & (1u << key)) { s->swallow &= ~(1u << key); return 0; }   /* this release ends the lock gesture */
    if (s->locked) { s->req = 8; return 0; }
    if (lv > 2) return 0;                                /* themes were already stepped through during the hold */
    if (lv) { s->req = 2 * key + lv + 1; return 0; }     /* 2,3 mode key  4,5 mains key  6,7 lamp key */
    if (key == K_LAMP && s->lmode) return 0;             /* the lamp is automatic: the key does not toggle it */
    return 1;
}

/* called once from main in place of its power-on delay */
void boot(u32 ms)
{
    struct S *s = st;
    for (u32 i = 0; i < sizeof(struct S); i++) ((volatile u8 *)s)[i] = 0;
    s->peak = 8; s->lastmode = MODE;
    if (SAVED[0] == SAVE_TAG) {
        u32 v = SAVED[1];
        if ((v & 0xFF) < 3) s->vol = v;
        if ((v >> 8 & 0xFF) < NTHEME) s->theme = v >> 8;
        if ((v >> 16 & 0xFF) < 3) s->lmode = v >> 16;
        if ((v >> 24) == 1) s->autom = 1;
    }
    play(s, TUNE, TICK40);
    DELAY(240); DELAY(240); DELAY(240);
    (void)ms;
}
