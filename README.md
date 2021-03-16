Mac下编译Linux、Windows64位可执行程序
```shell
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o v view.go
CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -o v view.go
```