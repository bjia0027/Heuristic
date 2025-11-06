#pragma once
#include "model_23.h"

class UIComponent23 {
public:
    UIComponent23();
    void render();
    void setModel(Model23* model);
private:
    Model23* model_;
};
