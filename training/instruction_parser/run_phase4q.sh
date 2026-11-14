while ! grep -q PHASE2B_DONE /root/logs/phase2b.log; do sleep 15; done
bash run_phase4.sh hf:google/gemma-4-E2B-it:A hf:google/gemma-4-E4B-it:C ft:/root/ckpt/s270m-full:B
