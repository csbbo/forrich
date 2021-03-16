package main

import (
	"os"
	"fmt"
	"net/http"
	"net/url"
	"io/ioutil"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Println("Useage: v <query1> <query2> ...")
		return
	}

	query_str := ""
	for i, param := range(os.Args) {
		if i != 0 {
			if i == 1 {
				query_str = query_str + "?s=" + url.QueryEscape(param)
			} else {
				query_str = query_str + "&s=" + url.QueryEscape(param)
			}
		}
	}
	resp, err := http.Get("http://60.205.223.161:9000" + query_str)
	if err != nil {
		fmt.Println("network error")
		return
	}
	defer resp.Body.Close()
	body, _ := ioutil.ReadAll(resp.Body)
	fmt.Println(string(body))
}