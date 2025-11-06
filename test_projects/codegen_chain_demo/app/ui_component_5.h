#pragma once
#include "model_5.h"

class UIComponent5 {
public:
    UIComponent5();
    void render();
    void setModel(Model5* model);
private:
    Model5* model_;
};
