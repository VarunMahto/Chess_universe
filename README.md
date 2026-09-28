# Chess Arcade

Original dark charcoal + eco-green chess arcade web game.

## Included features

- Email/password accounts with name, birth date and country
- Skill onboarding: beginner, rules/basic, strategy/tactics, tournament player
- Clickable profile avatar with + menu
- Preset avatars and draggable circular profile-image cropper
- Country flag beside usernames and online VS display
- Unique player code, player search and friend requests/acceptance
- 10-player clans and clan chat with home-page preview
- Elo rating, peak-Elo permanent rank and XP levels
- Wood, Bronze, Silver, Gold, Diamond, Master (ruby), Grand Master (orange-fire) ranks
- 50 missions, each with 3 phases, progress bars, manual claim and coin/XP rewards
- Offline, Computer and Online modes
- Computer levels: Beginner, Easy, Medium, Hard, Very Hard
- Online quick matchmaking, private rooms, public rooms and room codes
- Custom HH:MM:SS timer, White/Black clocks, timer on left, no-timer full board
- Legal chess moves, drag-and-drop, captures, castling, en passant, promotion choice, check, checkmate and draw rules
- Promotion to Queen, Rook, Bishop or Knight
- Captured pieces, move history, last-move arrow, legal-move markers and check animation
- Probability bar, player level display and quick chat
- Game-end popup with win/loss/draw, reward, Home and New Game
- Coins earned in Computer/Online modes; online losses deduct coins, computer losses do not
- Fair Play Guard rules and server-side online move validation
- Coaching book with study lessons
- Interactive mate-in-one puzzle board
- Board Collection with many increasing-price designs
- Settings limited to Sound, Music and Board selection
- Separate Your Progress and Board Collection pages

## Local run

```bash
pip install -r requirements.txt
python app.py
```

## Render

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

For persistent accounts and progress on Render, connect PostgreSQL through `DATABASE_URL`.
