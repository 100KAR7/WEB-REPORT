#!/usr/bin/env bash
# =============================================================================
# cron_setup.sh
# =============================================================================
# Complete guide for running AI Web Tester automatically via cron.
#
# Steps:
#   1. Make this script executable:   chmod +x cron_setup.sh
#   2. Edit the VARIABLES section below to match your setup
#   3. Run:  ./cron_setup.sh install
#   4. Verify:  crontab -l
#
# Usage:
#   ./cron_setup.sh install    — add cron jobs
#   ./cron_setup.sh remove     — remove all AI Web Tester cron jobs
#   ./cron_setup.sh test       — do a dry run right now
#   ./cron_setup.sh status     — show current crontab
# =============================================================================

# ── EDIT THESE VARIABLES ──────────────────────────────────────────────────
PROJECT_DIR="/path/to/ai_web_tester"          # absolute path to project root
PYTHON="/usr/bin/python3"                      # python binary (use venv path if applicable)
CONFIG="$PROJECT_DIR/pipeline/sites.yaml"     # path to your sites.yaml
LOG_DIR="$PROJECT_DIR/logs"                   # where .log files go
OUTPUT_DIR="$PROJECT_DIR/output"              # where reports go

# Notification email (leave blank to disable)
NOTIFY_EMAIL=""

# ── CRON SCHEDULE REFERENCE ───────────────────────────────────────────────
#  ┌──────── minute      (0-59)
#  │ ┌────── hour        (0-23)
#  │ │ ┌──── day of month (1-31)
#  │ │ │ ┌── month       (1-12)
#  │ │ │ │ ┌ day of week  (0-7, 0 and 7 = Sunday)
#  │ │ │ │ │
#  * * * * *  command
# ─────────────────────────────────────────────────────────────────────────

# ── BUILD THE COMMANDS ────────────────────────────────────────────────────
BASE_CMD="cd $PROJECT_DIR && $PYTHON pipeline/automated_runner.py \
  --config $CONFIG \
  --output $OUTPUT_DIR \
  --log-dir $LOG_DIR"

# Add email flag if set
if [ -n "$NOTIFY_EMAIL" ]; then
  BASE_CMD="$BASE_CMD --notify $NOTIFY_EMAIL"
fi

# Redirect cron output to a persistent log (cron's own stdout is /dev/null by default)
CRON_LOG="$LOG_DIR/cron.log"
FULL_CMD="$BASE_CMD >> $CRON_LOG 2>&1"

install_crons() {
  echo "Installing cron jobs..."
  mkdir -p "$LOG_DIR" "$OUTPUT_DIR"

  # Read current crontab (ignore error if empty)
  EXISTING=$(crontab -l 2>/dev/null || true)

  # Remove any old AI Web Tester entries
  CLEANED=$(echo "$EXISTING" | grep -v "automated_runner.py" || true)

  # ── Add new schedules ────────────────────────────────────────────────────
  NEW_CRONS=$(cat <<EOF

# ── AI Web Tester ──────────────────────────────────────────────────────────
# Full run every day at 2:00 AM
0 2 * * *   $FULL_CMD

# Quick run every 6 hours (SEO-only, faster)
0 */6 * * * cd $PROJECT_DIR && $PYTHON pipeline/automated_runner.py --config $CONFIG --no-ui --output $OUTPUT_DIR --log-dir $LOG_DIR >> $CRON_LOG 2>&1

# Full run every Monday at 6:00 AM (deep audit with email)
0 6 * * 1   $BASE_CMD --notify $NOTIFY_EMAIL >> $CRON_LOG 2>&1

# ── End AI Web Tester ──────────────────────────────────────────────────────
EOF
  )

  # Install updated crontab
  echo "$CLEANED$NEW_CRONS" | crontab -
  echo "✓ Cron jobs installed. Run 'crontab -l' to verify."
}

remove_crons() {
  echo "Removing AI Web Tester cron jobs..."
  EXISTING=$(crontab -l 2>/dev/null || true)
  CLEANED=$(echo "$EXISTING" | grep -v "automated_runner.py" \
    | grep -v "AI Web Tester" \
    | grep -v "End AI Web Tester" || true)
  echo "$CLEANED" | crontab -
  echo "✓ Cron jobs removed."
}

test_run() {
  echo "Running dry-run test now..."
  cd "$PROJECT_DIR"
  $PYTHON pipeline/automated_runner.py \
    --config "$CONFIG" \
    --dry-run \
    --output "$OUTPUT_DIR" \
    --log-dir "$LOG_DIR" \
    --log-level DEBUG
  echo "✓ Dry run complete. Check $LOG_DIR for output."
}

show_status() {
  echo "Current crontab:"
  echo "─────────────────────────────────────────────────────"
  crontab -l 2>/dev/null || echo "(no crontab installed)"
  echo "─────────────────────────────────────────────────────"
  echo ""
  echo "Recent log entries ($CRON_LOG):"
  echo "─────────────────────────────────────────────────────"
  tail -20 "$CRON_LOG" 2>/dev/null || echo "(log file not found — has it run yet?)"
}

# ── ENTRY POINT ───────────────────────────────────────────────────────────
case "${1:-help}" in
  install) install_crons ;;
  remove)  remove_crons  ;;
  test)    test_run      ;;
  status)  show_status   ;;
  *)
    echo "Usage: $0 {install|remove|test|status}"
    echo ""
    echo "  install  — add cron jobs to crontab"
    echo "  remove   — remove all AI Web Tester cron jobs"
    echo "  test     — run a dry-run right now"
    echo "  status   — show crontab and recent log"
    exit 1
    ;;
esac
