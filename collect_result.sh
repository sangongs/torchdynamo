function collect_dir() {
    real_dir_name=result/$model_name/${mode}_$1
    if [ -e $real_dir_name ]
    then
        last_print=`tail -n1 $real_dir_name/test.out`
        if [[ "$last_print" =~ "x p=" ]] || [[ "$last_print" =~ "x SAME" ]]
        then
            pvalue=`echo $last_print | awk -F' ' '{print $2}'`
            metrics=`tail -n1 $real_dir_name/inductor.csv`
            echo $model_name,$mode,$1,$metrics,$pvalue
            return
        fi
    fi
    echo $model_name,$mode,$1,,,,,,,,
}

echo model_name,mode,setting,dev,name,batch_size,speedup,compilation_latency,compression_ratio,pvalue
for model_name in $@
do
    for mode in eval training
    do
        collect_dir 'default'
        collect_dir 'warmup'
        collect_dir 'notune'
        collect_dir 'novertical'
        collect_dir 'nohorizontal'
        collect_dir 'nofuse'
        for warps in 1 2 4 8 12 16 20 24 28 32
        do
            collect_dir "WARPS_$warps"
        done
        for stages in 1 2 4 8 12
        do
            collect_dir "STAGES_$stages"
        done
    done
done