param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$Args
)

node "$PSScriptRoot\node_modules\tsx\dist\cli.mjs" "$PSScriptRoot\src\cli\index.ts" @Args
