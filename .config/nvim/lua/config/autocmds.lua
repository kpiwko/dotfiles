local group = vim.api.nvim_create_augroup("user_config", { clear = true })

-- Enable wrapping for prose, not source code
vim.api.nvim_create_autocmd("FileType", {
    group = group,
    pattern = {
        "gitcommit",
        "markdown",
        "text",
    },
    callback = function()
        vim.opt_local.wrap = true
        vim.opt_local.spell = true
    end,
})

-- Highlight copied text briefly
vim.api.nvim_create_autocmd("TextYankPost", {
    group = group,
    callback = function()
        vim.highlight.on_yank({ timeout = 150 })
    end,
})

-- Return to the previous position in a file
vim.api.nvim_create_autocmd("BufReadPost", {
    group = group,
    callback = function(event)
        local mark = vim.api.nvim_buf_get_mark(event.buf, '"')
        local line_count = vim.api.nvim_buf_line_count(event.buf)

        if mark[1] > 0 and mark[1] <= line_count then
            pcall(vim.api.nvim_win_set_cursor, 0, mark)
        end
    end,
})
