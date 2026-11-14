#!/bin/bash
# Source this in EVERY shell that starts the sim or a client of it (check, snap, baseline, eval):
#   source /root/venue_look/venue_env.sh
# AALTO_LOOK = appearance + head camera pose. AALTO_SCENE = geometry (bin wall height); the sim and its clients
# must agree on it, or the oracle and the scoring use the wrong bin size.
D="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export AALTO_LOOK="$D/venue.yaml"
if [ -f "$D/scene_venue.yaml" ]; then export AALTO_SCENE="$D/scene_venue.yaml"; fi
