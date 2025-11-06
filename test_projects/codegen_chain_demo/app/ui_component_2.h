#pragma once
#include "model_2.h"

class UIComponent2 {
public:
    UIComponent2();
    void render();
    void setModel(Model2* model);
private:
    Model2* model_;
};
