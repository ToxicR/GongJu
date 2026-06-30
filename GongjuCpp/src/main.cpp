#include <windows.h>
#include "main_window.h"

int WINAPI wWinMain(HINSTANCE, HINSTANCE, LPWSTR, int nCmdShow) {
    InitCommonControls();
    register_main_window_class();
    HWND hMain = create_main_window();
    if (!hMain) return 1;
    ShowWindow(hMain, nCmdShow);
    MSG msg;
    while (GetMessage(&msg, nullptr, 0, 0)) {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }
    return (int)msg.wParam;
}
