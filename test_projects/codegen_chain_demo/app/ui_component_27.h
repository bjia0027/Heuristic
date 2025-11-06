#pragma once
#include "model_27.h"

class UIComponent27 {
public:
    UIComponent27();
    void render();
    void setModel(Model27* model);
private:
    Model27* model_;
};
