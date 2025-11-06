#pragma once
#include "model_12.h"

class UIComponent12 {
public:
    UIComponent12();
    void render();
    void setModel(Model12* model);
private:
    Model12* model_;
};
