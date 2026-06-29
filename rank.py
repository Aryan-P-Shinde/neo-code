#!/usr/bin/env python3
"""
CLI entry point — thin wrapper around ranker.py
Usage: python rank.py --candidates ./candidates.jsonl --out ./submission.csv
"""
import argparse
from ranker import rank_candidates

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Redrob Candidate Ranker')
    parser.add_argument('--candidates', required=True, help='Path to candidates.jsonl')
    parser.add_argument('--out', required=True, help='Output CSV path')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    rank_candidates(args.candidates, args.out, verbose=args.verbose)
