#!/bin/bash
# Start the sim with the venue look (appearance, head camera pose, and scene_venue.yaml geometry if it exists).
source "$(dirname "${BASH_SOURCE[0]}")/venue_env.sh"
cd /root/aaltonomous-humanoid && bash aaltonomous/cloud/aalto.sh sim "$@"
