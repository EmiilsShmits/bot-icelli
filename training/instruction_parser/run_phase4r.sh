while ! grep -q PHASE4_DONE /root/logs/phase4b.log; do sleep 15; done
bash run_phase4.sh ft:/root/ckpt/s1b-full:B
