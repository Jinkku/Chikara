Backup of the user profile page as it was on 2026-11-13, before the redesign.

The classic page is also still live in code: Chikara/views.py keeps it as user_classic().
- Preview it any time:  /user/<name>?classic=1
- Switch the whole site back: set PROFILE_CLASSIC = True in Chikara/views.py and restart daphne.

These files are plain copies of the originals in case you want to restore them by hand.
