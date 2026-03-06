#!/bin/zsh

findTool codex || { logmsg FATAL "Make sure to nvminit first"; exit 1 }

script_dir=${0:a:h}
screenshotpath=${1?First parameter must be path to screenshot png}
jsonfileroot=${screenshotpath:r:t}

showeval ${=TOOL_CODEX} exec \
    -C ${script_dir} \
    -i ${screenshotpath} \
    --full-auto \
    -o codex-last-${jsonfileroot}.txt \
    "Convert the attached screenshot into ${jsonfileroot}.json using SCREENSHOT_EXTRACTION_RULES.md and save it in repo root."

# vim: ft=zsh
