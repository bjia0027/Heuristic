#pragma once
#include "service_8.h"
#include "model_8.h"
#include <memory>

class Controller8 {
public:
    Controller8();
    void initialize();
    void run();
private:
    std::unique_ptr<Service8> service_;
    std::shared_ptr<Model8> model_;
};
