" Keep classic Vim mode behavior explicit
set nocompatible

" Syntax/filetype support
syntax on
filetype plugin indent on

" Colors
set termguicolors
set background=light

" Line numbers
set number
set numberwidth=4

" Text width / wrapping
" Keeping these disabled because they are currently commented in your config,
" and enabling them would change editing behavior.
set tw=108
set wrap

" Tabs / indentation
set tabstop=4
set shiftwidth=4
set expandtab

" Parentheses / matching delimiters
set showmatch

" Mouse support
set mouse=a

" Status / command area
"set showmode
"set noshowcmd

" Ruler
set noruler

" Searching
" Keeping incsearch disabled because you explicitly had it commented out.
" If you want live incremental search feedback, uncomment this:
set incsearch
set ignorecase
set smartcase
set hlsearch

" Scrolling comfort
set scrolloff=4

" Backspace behavior
set backspace=2

" Wildmenu / command-line completion
set wildmenu
set wildmode=longest:full,full

" Spell check
" set spell

" Native macOS clipboard
set clipboard=unnamed

" Optional explicit clipboard mappings
nnoremap <leader>y "+y
vnoremap <leader>y "+y
nnoremap <leader>p "+p
nnoremap <leader>P "+P
" Added:
" These are useful even with unnamedplus because they let you be explicit when needed.

" Optional macOS command fallback
vnoremap <leader>Y :w !pbcopy<CR><CR>
nnoremap <leader>PP :r !pbpaste<CR>

" Status line
set laststatus=2
set statusline=
set statusline+=%f\ " filename
set statusline+=%h%m%r%w " status flags
set statusline+=\[%{strlen(&ft)?&ft:'none'}] " file type
set statusline+=%= " right align remainder
set statusline+=0x%-8B " character value
set statusline+=%-14(%l,%c%V%) " line, character

" Disable file modelines
set nomodeline
