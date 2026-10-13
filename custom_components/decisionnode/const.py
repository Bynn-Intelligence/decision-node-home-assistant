"""Constants of the DecisionNode integration."""

from __future__ import annotations

DOMAIN = "decisionnode"

CONF_MODEL = "model"
CONF_STANDING = "standing_questions"
CONF_FRIGATE = "frigate"

DEFAULT_MODEL = "decisionnode-moe"

# Standing questions: how often each is asked, and the least it may be.
DEFAULT_INTERVAL = 60
MIN_INTERVAL = 10
DEFAULT_THRESHOLD = 0.5

# Every call of one config entry is spaced by at least this many seconds, and at most
# this many run at once, so automations cannot flood the API.
MIN_SPACING = 1.0
MAX_CONCURRENT = 2

# Frigate: the topic Frigate publishes its events on, and the least time between two
# decisions for the same camera.
DEFAULT_FRIGATE_TOPIC = "frigate/events"
DEFAULT_FRIGATE_COOLDOWN = 30

EVENT_DECISION = "decisionnode_decision"
SERVICE_DECIDE = "decide"
