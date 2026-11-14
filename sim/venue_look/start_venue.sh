#!/bin/bash
# Start the sim with the venue look (appearance only; geometry stays Aalto scene.yaml).
export AALTO_LOOK=/root/venue_look/venue.yaml
cd /root/aaltonomous-humanoid && bash aaltonomous/cloud/aalto.sh sim "$@"
