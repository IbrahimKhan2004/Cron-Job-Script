#!/bin/bash
gunicorn app:app & python main.py
