#!/bin/bash
func=GetNoteFunction
sam build && sam local invoke $func -e events/event.json
#sam build && sam local invoke $func -e events/event.json
