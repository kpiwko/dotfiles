local parsers = {
    -- Shell
    "bash",

    -- Web / React
    "html",
    "css",
    "javascript",
    "typescript",
    "tsx",

    -- Other languages
    "go",
    "gomod",
    "gosum",
    "gowork",
    "json",
    "markdown",
    "markdown_inline",
    "python",
    "yaml",

    -- Neovim configuration
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
            require("nvim-treesitter").install(parsers)

            -- JSONC uses the JSON parser
            vim.treesitter.language.register("json", "jsonc")

            vim.api.nvim_create_autocmd("FileType", {
                callback = function()
                    pcall(vim.treesitter.start)
                end,
            })
        end,
    },
}

