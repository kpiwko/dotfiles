local opt = vim.opt

-- Interface
opt.number = true
opt.numberwidth = 4
opt.signcolumn = "yes"
opt.cursorline = true
opt.termguicolors = true

-- Editing
opt.expandtab = true
opt.tabstop = 4
opt.shiftwidth = 4
opt.shiftround = true
opt.smartindent = true

-- Searching
opt.ignorecase = true
opt.smartcase = true
opt.incsearch = true
opt.hlsearch = true

-- Scrolling and splits
opt.scrolloff = 6
opt.sidescrolloff = 8
opt.splitbelow = true
opt.splitright = true

-- Completion
opt.completeopt = { "menu", "menuone", "noselect" }
opt.wildmode = { "longest:full", "full" }

-- Files
opt.undofile = true
opt.swapfile = false
opt.backup = false
opt.writebackup = false
opt.modeline = false

-- Responsiveness
opt.updatetime = 250
opt.timeoutlen = 400

-- Text display
opt.wrap = false
opt.linebreak = true
opt.breakindent = true
opt.colorcolumn = "108"
opt.textwidth = 0

-- Status
opt.laststatus = 3
opt.showmode = false

-- macOS clipboard
opt.clipboard = "unnamedplus"
