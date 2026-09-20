#ifndef PATHHIJACKER_TCC_COMPAT_H
#define PATHHIJACKER_TCC_COMPAT_H

#ifndef CP_UTF8
#define CP_UTF8 65001
#endif

int __stdcall MultiByteToWideChar(unsigned, unsigned long, const char *, int, wchar_t *, int);

#endif
