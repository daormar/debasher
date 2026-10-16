# Build one array element per worker task
local w=$(debasher::read_opt_value_from_line "${cmdline}" "-w")
local array=()
for ((i=0; i<w; i++)); do
    array+=("$i")
done
