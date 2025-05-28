#!/bin/bash

docker build -t engine . 
docker run -d -p 8080:8080 engine

