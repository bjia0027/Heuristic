#pragma once
#include <functional>
#include <vector>

class Service18 {
public:
    Service18();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
