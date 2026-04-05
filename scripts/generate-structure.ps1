function Show-Tree {
    param ($path = ".", $indent = "")

    $exclude = @(
        "__pycache__", "node_modules", ".venv", "venv",
        ".git", "dist", "build", ".next", ".cache",
        ".idea", ".vscode"
    )

    # FIXED: Proper hash table syntax for sorting multiple properties
    $items = Get-ChildItem $path | Where-Object {
        $exclude -notcontains $_.Name
    } | Sort-Object @{Expression='PSIsContainer'; Descending=$true}, @{Expression='Name'; Ascending=$true}

    for ($i = 0; $i -lt $items.Count; $i++) {
        $item = $items[$i]
        $isLast = ($i -eq $items.Count - 1)

        $prefix = if ($isLast) { "└── " } else { "├── " }
        $nextIndent = if ($isLast) { "$indent    " } else { "$indent│   " }

        if ($item.PSIsContainer) {
            "$indent$prefix$($item.Name)/"
            Show-Tree $item.FullName $nextIndent
        } else {
            "$indent$prefix$($item.Name)"
        }
    }
}

# Generate structure.txt in root
Show-Tree | Out-File "structure.txt" -Encoding utf8
Write-Host "✅ structure.txt generated successfully!"