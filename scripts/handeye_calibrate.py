#!/usr/bin/env python3
"""Solve OpenCV hand-eye calibration from a CSV pose dataset."""

import argparse
import csv

import cv2
import numpy as np


def read_rows(path):
    with open(path, newline='', encoding='utf-8') as stream:
        rows = list(csv.DictReader(stream))
    required = {'gripper2base_r', 'gripper2base_t', 'target2cam_r', 'target2cam_t'}
    if not rows or not required.issubset(rows[0]):
        raise ValueError('CSV must contain gripper2base_r/t and target2cam_r/t columns')
    result = []
    for row in rows:
        result.append((
            np.asarray(row['gripper2base_r'].split(), dtype=float).reshape(3, 3),
            np.asarray(row['gripper2base_t'].split(), dtype=float).reshape(3, 1),
            np.asarray(row['target2cam_r'].split(), dtype=float).reshape(3, 3),
            np.asarray(row['target2cam_t'].split(), dtype=float).reshape(3, 1),
        ))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, help='CSV pose dataset')
    parser.add_argument('--output', required=True, help='YAML output path')
    parser.add_argument('--mode', choices=('eye_in_hand', 'eye_to_hand'), default='eye_in_hand')
    args = parser.parse_args()
    rows = read_rows(args.input)
    if len(rows) < 4:
        raise ValueError('At least 4 pose pairs are required; 10-20 varied poses are recommended')
    r_g2b, t_g2b, r_t2c, t_t2c = zip(*rows)
    result_r, result_t = cv2.calibrateHandEye(
        list(r_g2b), list(t_g2b), list(r_t2c), list(t_t2c),
        method=cv2.CALIB_HAND_EYE_TSAI
    )
    result_name = 'camera_to_gripper' if args.mode == 'eye_in_hand' else 'camera_to_base'
    storage = cv2.FileStorage(args.output, cv2.FILE_STORAGE_WRITE)
    storage.write('mode', args.mode)
    storage.write(result_name + '_rotation', result_r)
    storage.write(result_name + '_translation', result_t)
    storage.release()
    print(f'Wrote {args.mode} result to {args.output}')


if __name__ == '__main__':
    main()
