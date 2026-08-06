local languages = {
    "go",
    "gomod",
    "gosum",
    "gowork",
    "javascript",
    "json",
    "jsonc",
    "markdown",
    "markdown_inline",
    "python",
    "tsx",
    "typescript",
    "yaml",

    -- Needed for editing your Neovim configuration
    "lua",
    "vim",
    "vimdoc",
    "query",
}

return {
    {
        "nvim-treesitter/nvim-treesitter",
        branch = "main",
        lazy = false,
        build = ":TSUpdate",

        config = function()
            require("nvim-treesitter").install(languages)

            vim.api.nvim_create_autocmd("FileType", {
                pattern = languages,
                callback = function()
                    vim.treesitter.start()
                end,
            })
        end,
    },
}
