import subprocess

profiles = {
    "1": ("Fastest route", "asp/profiles/profile_fastest.lp"),
    "2": ("Least waiting", "asp/profiles/profile_least_waiting.lp"),
    "3": ("Fewest transfers", "asp/profiles/profile_fewest_transfers.lp"),
    "4": ("Balanced recommendation", "asp/profiles/profile_balanced.lp"),
}

print("Choose user preference:")
for key, (name, _) in profiles.items():
    print(f"{key}. {name}")

choice = input("Enter option number: ").strip()

if choice not in profiles:
    print("Invalid choice.")
    exit(1)

name, profile_file = profiles[choice]

print(f"\nSelected: {name}")
print("Running ASP + Flatland solver...\n")

cmd = [
    "python",
    "solve.py",
    "envs/pkl/env_001--2_4.pkl",
    profile_file
]

subprocess.run(cmd)