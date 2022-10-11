

INDUCTOR_TRITON_AUTOTUNE=1
INDUCTOR_CAN_FUSE_VERTICAL=1
INDUCTOR_CAN_FUSE_HORIZONTAL=1
INDUCTOR_TRITON_NUMWARPS=0
INDUCTOR_TRITON_NUMSTAGES=0

OUTPUTS="test.out inductor.csv inductor_compilation_metrics.csv"

function run_and_collect() {
    real_dir_name=result/$model_name/eval_$dir_name
    echo "Running $real_dir_name"
    rm -fr $OUTPUTS
    rm -fr $real_dir_name
    INDUCTOR_TRITON_AUTOTUNE=$INDUCTOR_TRITON_AUTOTUNE \
    INDUCTOR_CAN_FUSE_VERTICAL=$INDUCTOR_CAN_FUSE_VERTICAL \
    INDUCTOR_CAN_FUSE_HORIZONTAL=$INDUCTOR_CAN_FUSE_HORIZONTAL \
    INDUCTOR_TRITON_NUMWARPS=$INDUCTOR_TRITON_NUMWARPS \
    INDUCTOR_TRITON_NUMSTAGES=$INDUCTOR_TRITON_NUMSTAGES  \
    benchmarks/torchbench.py -d cuda --float32 --inductor --no-skip --performance --only $model_name --verbose &> test.out
    mkdir -p $real_dir_name
    mv $OUTPUTS $real_dir_name

    real_dir_name=result/$model_name/training_$dir_name
    echo "Running $real_dir_name"
    rm -fr $OUTPUTS
    rm -fr $real_dir_name
    INDUCTOR_TRITON_AUTOTUNE=$INDUCTOR_TRITON_AUTOTUNE \
    INDUCTOR_CAN_FUSE_VERTICAL=$INDUCTOR_CAN_FUSE_VERTICAL \
    INDUCTOR_CAN_FUSE_HORIZONTAL=$INDUCTOR_CAN_FUSE_HORIZONTAL \
    INDUCTOR_TRITON_NUMWARPS=$INDUCTOR_TRITON_NUMWARPS \
    INDUCTOR_TRITON_NUMSTAGES=$INDUCTOR_TRITON_NUMSTAGES  \
    benchmarks/torchbench.py -d cuda --float32 --inductor --no-skip --performance --only $model_name --verbose --training &> test.out
    mkdir -p $real_dir_name
    mv $OUTPUTS $real_dir_name
}

for model_name in $@
do
    dir_name="warmup"
    run_and_collect

    dir_name="default"
    run_and_collect

    dir_name="notune"
    INDUCTOR_TRITON_AUTOTUNE=0
    run_and_collect
    INDUCTOR_TRITON_AUTOTUNE=1

    dir_name="novertical"
    INDUCTOR_CAN_FUSE_VERTICAL=0
    run_and_collect
    INDUCTOR_CAN_FUSE_VERTICAL=1

    dir_name="nohorizontal"
    INDUCTOR_CAN_FUSE_HORIZONTAL=0
    run_and_collect
    INDUCTOR_CAN_FUSE_HORIZONTAL=1

    dir_name="nofuse"
    INDUCTOR_CAN_FUSE_VERTICAL=0
    INDUCTOR_CAN_FUSE_HORIZONTAL=0
    run_and_collect
    INDUCTOR_CAN_FUSE_VERTICAL=1
    INDUCTOR_CAN_FUSE_HORIZONTAL=1

    for INDUCTOR_TRITON_NUMWARPS in 1 2 4 8 12 16 20 24 28 32
    do
        dir_name="WARPS_$INDUCTOR_TRITON_NUMWARPS"
        run_and_collect
    done
    INDUCTOR_TRITON_NUMWARPS=0

    for INDUCTOR_TRITON_NUMSTAGES in 1 2 4 8 12
    do
        dir_name="STAGES_$INDUCTOR_TRITON_NUMSTAGES"
        run_and_collect
    done
    INDUCTOR_TRITON_NUMSTAGES=0
done