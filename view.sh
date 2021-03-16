if [[ $# < 1 ]]; then
    echo "Useage: v <query1> <query2> ..."
    exit -1
fi

is_first="true"
for i in $*
do
    if [[ $is_first == "true" ]]; then
        param+="?s="`echo $i | tr -d '\n' | xxd -plain | sed 's/\(..\)/%\1/g'`
    else
        param+="&s="`echo $i | tr -d '\n' | xxd -plain | sed 's/\(..\)/%\1/g'`
    fi
    is_first="false"
done

curl "http://60.205.223.161:9000"$param
echo ""
