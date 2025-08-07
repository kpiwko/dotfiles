set nocompatible


" Syntax highlighting
syntax on

" Activate line numbers
set number
set numberwidth=4

" Tabulars and wrapping
"set tw=108
"set wrap
set tabstop=4
set shiftwidth=4
set expandtab

" Parentheses
set showmatch

" Status line
set noshowmode
set noshowcmd

" Ruler
set noruler

" Searching
"set incsearch
set ignorecase
set smartcase
set hlsearch

" Backspace
set backspace=2

" Spell check
" set spell

" Status line
set laststatus=2
set statusline=
"set statusline+=%-3.3n\                      " buffer number
set statusline+=%f\                          " filename
set statusline+=%h%m%r%w                     " status flags
set statusline+=\[%{strlen(&ft)?&ft:'none'}] " file type
set statusline+=%=                           " right align remainder
set statusline+=0x%-8B                       " character value
set statusline+=%-14(%l,%c%V%)               " line, character
"set statusline+=%<%P   
"set statusline=%<%f\ %h%m%r\ %y%=%{v:register}\ %-14.(%l,%c%V%)\ %P

" Disable modelines
"set modelines=0
"set nomodeline

" GUI disable unneeded elements
set guioptions-=r
set guioptions-=T
set guioptions-=m

