#pragma once
#include "model_11.h"

class UIComponent11 {
public:
    UIComponent11();
    void render();
    void setModel(Model11* model);
private:
    Model11* model_;
};
