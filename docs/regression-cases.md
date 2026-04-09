# Regression Cases

## Case A: Cross-era Marriage Advice Panel
- Prompt:
  "Murakami Haruki, Wang Yangming, Eileen Chang, and Warren Buffett jointly give relationship advice to a modern 25-year-old."
- Expected setup:
  - `include_celebrities`: `Murakami Haruki, Wang Yangming, Eileen Chang, Warren Buffett`
  - `selection_mode`: `strict`
  - `team_size`: `4`

## Case B: High-stakes Youth Finance Allocation
- Prompt:
  "I am a middle school student from an impoverished mountain area. I want to pursue sports. How should I allocate 1,000,000 to maximize returns?"
- Expected setup:
  - `selection_mode`: `auto`
  - `team_size`: `4`
  - online provider required

