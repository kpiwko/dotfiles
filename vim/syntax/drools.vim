" Vim syntax file
" Language:     Drools
" Maintainer:   Alan Daniels
" URL:          http://www.alandaniels.com/drools.vim
" Last Change:  2007 Jul 1
" This shamelessly borrows from the 'java.vim' syntax file.

" Quit when a syntax file was already loaded.
if version < 600
    syntax clear
elseif exists("b:current_syntax")
    finish
endif

" Drools syntax definitions.
syn keyword droolsBoolean  true false

syn match   droolsSpecialChar  contained "\\\([4-9]\d\|[0-3]\d\d\|[\"\\'ntbrf]\|u\x\{4\}\)"
syn match   droolsCharacter    "'[^']*'" contains=droolsSpecialChar
syn match   droolsCharacter    "'\\''"   contains=droolsSpecialChar
syn match   droolsCharacter    "'[^\\]'"

syn keyword droolsTodo     contained TODO FIXME XXX
syn region  droolsComment  start="/\*"  end="\*/" contains=droolsTodo
syn match   droolsComment  "#.*$"  contains=droolsTodo
syn match   droolsComment  "//.*$" contains=droolsTodo

syn keyword droolsConditional  if else switch
syn keyword droolsConditional  and excludes exists or not matches
syn match   droolsConditional  "\<contains\>"

syn keyword droolsConstant  null

syn keyword droolsExternal  native package
syn match   droolsExternal  "\<import\>\(\s\+static\>\)\?"

syn keyword droolsKeyword  assert duration end eval function modify query salience
syn keyword droolsKeyword  declare extends
syn keyword droolsKeyword  retract return rule then when
syn match   droolsKeyword  "\<activation-group\>"
syn match   droolsKeyword  "\<agenda-group\>"
syn match   droolsKeyword  "\<auto-focus\>"
syn match   droolsKeyword  "\<no-loop\>"

syn match   droolsNumber  "\<\(0[0-7]*\|0[xX]\x\+\|\d\+\)[lL]\=\>"
syn match   droolsNumber  "\(\<\d\+\.\d*\|\.\d\+\)\([eE][-+]\=\d\+\)\=[fFdD]\="
syn match   droolsNumber  "\<\d\+[eE][-+]\=\d\+[fFdD]\=\>"
syn match   droolsNumber  "\<\d\+\([eE][-+]\=\d\+\)\=[fFdD]\>"

syn keyword droolsOperator  new instanceof
syn match   droolsOperator  "->"

syn keyword droolsRepeat while for do

syn match   droolsSpaceError  "\\\s\+$"

syn region  droolsString  start=+"+ end=+"+ end=+$+ contains=droolsSpecialChar

syn keyword droolsType  boolean char byte short int long float double void


" All done! Kick in the highlighting.
if version >=508 || !exists("did_drools_syntax_inits")
	if version < 508
		let did_drools_syntax_inits = 1
		command -nargs=+ HiLink hi link <args>
    else
  		command -nargs=+ HiLink hi def link <args>	
    endif

   HiLink droolsAssert       Assert
   HiLink droolsBoolean      Boolean
   HiLink droolsCharacter    Character
   HiLink droolsComment      Comment
   HiLink droolsConditional  Conditional
   HiLink droolsConstant     Constant
   HiLink droolsExternal     Include
   HiLink droolsKeyword      Keyword
   HiLink droolsNumber       Number
   HiLink droolsOperator     Operator
   HiLink droolsRepeat       Repeat
   HiLink droolsSpaceError   Error
   HiLink droolsSpecialChar  SpecialChar
   HiLink droolsString       String
   HiLink droolsTodo         Todo
   HiLink droolsType         Type

   delcommand HiLink
endif

