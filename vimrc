set nocompatible

" Pathogen plugin manager
execute pathogen#infect()

" Syntax highlighting
syntax on
filetype plugin indent on

set t_Co=256
colorscheme eclipse

" tmux integration
let g:tmuxline_powerline_separators = 0

"if &term =~ '256color'
  " Disable Background Color Erase (BCE) so that color schemes
  " work properly when Vim is used inside tmux and GNU screen.
  " See also http://snk.tuxfamily.org/log/vim-256color-bce.html
  "set t_ut=
"endif

" crtlp integration - for project viewing
let g:ctrlp_map = '<c-p>'
let g:ctrlp_cmd = 'CtrlP'
let g:ctrlp_custom_ignore = {
    \ 'dir':  '\v[\/](target)\v[\/]$',
    \ 'file': '\v\.(class)$',
    \ }

"multibuffer support
set hidden

" Activate line numbers
set number
set numberwidth=4

" Tabulars
" set tw=128
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
"set statusline=
"set statusline+=%-3.3n\                      " buffer number
"set statusline+=%f\                          " filename
"set statusline+=%h%m%r%w                     " status flags
"set statusline+=\[%{strlen(&ft)?&ft:'none'}] " file type
"set statusline+=%=                           " right align remainder
"set statusline+=0x%-8B                       " character value
"set statusline+=%-14(%l,%c%V%)               " line, character
"set statusline+=%<%P   
"set statusline=%<%f\ %h%m%r\ %y%=%{v:register}\ %-14.(%l,%c%V%)\ %P

" Disable modelines
set modelines=0
set nomodeline

" XML folding
"let g:xml_syntax_folding=1
"au FileType xml setlocal foldmethod=syntax

" OmniCompletition
"inoremap <C-Space> <C-x><C-o>
inoremap <C-@> <C-x><C-o>

" Asciidoc
au BufRead,BufNewFile *.asciidoc :set filetype=asciidoc
au BufRead,BufNewFile *.adoc :set filetype=asciidoc

" Antlr
au BufRead,BufNewFile *.g :set filetype=antlr
au BufRead,BufNewFile *.pom :set filetype=xml
au BufRead,BufNewFile *.gradle :set filetype=groovy

" Drools
au BufRead,BufNewFile *.drl :set filetype=drools

" Markdown
au BufRead,BufNewFile *.md :set filetype=markdown

au FileType tex setlocal tw=128 formatoptions+=t spell expandtab
au FileType xml setlocal tw=128 tabstop=4 shiftwidth=4 spell expandtab 
au FileType java setlocal tw=128 tabstop=4 shiftwidth=4 expandtab nowrap
au FileType yaml setlocal tw=128 tabstop=2 shiftwidth=2 expandtab nowrap
au FileType markdown setlocal spell
au FileType asciidoc setlocal spell

" GUI disable unneeded elements
set guioptions-=r
set guioptions-=T
set guioptions-=m

"  files
set dir=/var/tmp/kpiwko-vim
set backupdir=/var/tmp/kpiwko-vim

" Macros
