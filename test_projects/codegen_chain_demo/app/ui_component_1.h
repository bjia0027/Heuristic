#pragma once
#include "model_1.h"

class UIComponent1 {
public:
    UIComponent1();
    void render();
    void setModel(Model1* model);
private:
    Model1* model_;
};
