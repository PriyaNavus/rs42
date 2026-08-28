
from pathlib import Path

ROOT = Path.cwd().resolve()

if not (ROOT / "solve.py").exists():
    raise SystemExit("ERROR: Run this from the RS42 repository root.")

E2 = ROOT / "tools" / "final_evaluation" / "build_e2_transfer_network.py"
E5 = ROOT / "tools" / "final_evaluation" / "build_e5_mixed_preferences.py"

for path in [E2, E5]:
    if not path.exists():
        raise SystemExit("Missing: {}".format(path))

# ------------------------------------------------------------
# E2
# ------------------------------------------------------------
s = E2.read_text(encoding="utf-8")

s = s.replace("WIDTH = 19", "WIDTH = 21")
s = s.replace("RELEASES = [0, 0, 7, 14]", "RELEASES = [0, 0, 8, 16]")
s = s.replace(
    "if STEPS != [22, 6, 6, 6]:",
    "if STEPS != [24, 7, 7, 7]:",
)
s = s.replace('fastest["journey"] != 20', 'fastest["journey"] != 23')
s = s.replace('fewest["journey"] != 22', 'fewest["journey"] != 24')

old_e2 = '''% Fixed service timetable for solver-balanced E2.
% Direct:   2 -> 24 = journey 22
% Transfer: 2 -> 8, 9 -> 15, 16 -> 22 = journey 20, wait 2
:- first_station_visit(0,origin,T), T != 2.
:- first_station_visit(0,destination,T), T != 24.

:- first_station_visit(1,origin,T), T != 2.
:- first_station_visit(1,station_b,T), T != 8.
:- first_station_visit(2,station_b,T), T != 9.
:- first_station_visit(2,station_c,T), T != 15.
:- first_station_visit(3,station_c,T), T != 16.
:- first_station_visit(3,destination,T), T != 22.'''

new_e2 = '''% Final E2 timetable using the actual route lengths.
% Direct:   2 -> 26 = journey 24
% Transfer: 2 -> 9, 10 -> 17, 18 -> 25 = journey 23, wait 2
:- first_station_visit(0,origin,T), T != 2.
:- first_station_visit(0,destination,T), T != 26.

:- first_station_visit(1,origin,T), T != 2.
:- first_station_visit(1,station_b,T), T != 9.
:- first_station_visit(2,station_b,T), T != 10.
:- first_station_visit(2,station_c,T), T != 17.
:- first_station_visit(3,station_c,T), T != 18.
:- first_station_visit(3,destination,T), T != 25.'''

if old_e2 not in s:
    raise SystemExit("ERROR: Expected E2 timetable block not found.")

s = s.replace(old_e2, new_e2, 1)
s = s.replace(
    'print("  Fastest: journey=20, transfers=2")',
    'print("  Fastest: journey=23, transfers=2")',
)
s = s.replace(
    'print("  Fewer Transfers: journey=22, transfers=0")',
    'print("  Fewer Transfers: journey=24, transfers=0")',
)

compile(s, str(E2), "exec")
E2.write_text(s, encoding="utf-8")

# ------------------------------------------------------------
# E5
# ------------------------------------------------------------
s = E5.read_text(encoding="utf-8")

s = s.replace(
    "RELEASES = [0, 0, 7, 14, 0, 11]",
    "RELEASES = [0, 0, 8, 16, 0, 12]",
)
s = s.replace(
    "if STEPS != [26, 6, 6, 6, 10, 11]:",
    "if STEPS != [30, 7, 7, 7, 11, 12]:",
)
s = s.replace('fastest["journey"] == 20', 'fastest["journey"] == 23')
s = s.replace('least["journey"] == 26', 'least["journey"] == 30')
s = s.replace('fewest["journey"] == 26', 'fewest["journey"] == 30')

old_e5 = '''% Fixed service timetable for solver-balanced E5.
% Direct:      2 -> 28 = journey 26, wait 0, transfers 0
% Fast:        2 -> 8, 9 -> 15, 16 -> 22
%              journey 20, wait 2, transfers 2
% Compromise:  2 -> 12, 13 -> 24
%              journey 22, wait 1, transfers 1
:- first_station_visit(0,origin,T), T != 2.
:- first_station_visit(0,destination,T), T != 28.

:- first_station_visit(1,origin,T), T != 2.
:- first_station_visit(1,station_b,T), T != 8.
:- first_station_visit(2,station_b,T), T != 9.
:- first_station_visit(2,station_c,T), T != 15.
:- first_station_visit(3,station_c,T), T != 16.
:- first_station_visit(3,destination,T), T != 22.

:- first_station_visit(4,origin,T), T != 2.
:- first_station_visit(4,station_h,T), T != 12.
:- first_station_visit(5,station_h,T), T != 13.
:- first_station_visit(5,destination,T), T != 24.'''

new_e5 = '''% Final E5 timetable using the actual route lengths.
% Direct:      2 -> 32 = journey 30, wait 0, transfers 0
% Fast:        2 -> 9, 10 -> 17, 18 -> 25
%              journey 23, wait 2, transfers 2
% Compromise:  2 -> 13, 14 -> 26
%              journey 24, wait 1, transfers 1
:- first_station_visit(0,origin,T), T != 2.
:- first_station_visit(0,destination,T), T != 32.

:- first_station_visit(1,origin,T), T != 2.
:- first_station_visit(1,station_b,T), T != 9.
:- first_station_visit(2,station_b,T), T != 10.
:- first_station_visit(2,station_c,T), T != 17.
:- first_station_visit(3,station_c,T), T != 18.
:- first_station_visit(3,destination,T), T != 25.

:- first_station_visit(4,origin,T), T != 2.
:- first_station_visit(4,station_h,T), T != 13.
:- first_station_visit(5,station_h,T), T != 14.
:- first_station_visit(5,destination,T), T != 26.'''

if old_e5 not in s:
    raise SystemExit("ERROR: Expected E5 timetable block not found.")

s = s.replace(old_e5, new_e5, 1)
s = s.replace("timeout=240,", "timeout=300,")

compile(s, str(E5), "exec")
E5.write_text(s, encoding="utf-8")

print("FINAL E2/E5 METRIC PATCH: SUCCESS")
print()
print("E2")
print("  movement = [24, 7, 7, 7]")
print("  Fastest  = journey 23, transfers 2")
print("  Direct   = journey 24, transfers 0")
print()
print("E5")
print("  movement = [30, 7, 7, 7, 11, 12]")
print("  Fast       = journey 23, wait 2, transfers 2")
print("  Compromise = journey 24, wait 1, transfers 1")
print("  Direct     = journey 30, wait 0, transfers 0")
print()
print(r"Run: python tools\final_evaluation\build_e2_transfer_network.py --overwrite")
print(r"Run: python tools\final_evaluation\build_e5_mixed_preferences.py --overwrite")
